from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, cast

from .time_machine import TimeMachineService
from .time_machine_api import TimeMachineAPI


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_len = handler.headers.get("Content-Length", "0")
    content_length = int(raw_len) if raw_len else 0
    if content_length <= 0:
        return {}
    body = handler.rfile.read(content_length)
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _error_payload(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


class TimeMachineHttpApp:
    def __init__(self, conn: sqlite3.Connection, static_dir: Path) -> None:
        self.api = TimeMachineAPI(TimeMachineService(conn))
        self.static_dir = static_dir


class TimeMachineRequestHandler(BaseHTTPRequestHandler):
    app_factory: Callable[[], TimeMachineHttpApp] | None = None

    def _app(self) -> TimeMachineHttpApp:
        if self.app_factory is None:
            raise RuntimeError("app_factory is not configured")
        return self.app_factory()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/seasons":
                _json_response(self, HTTPStatus.OK, self._app().api.get_seasons())
                return

            match = re.fullmatch(r"/api/seasons/(\d+)/matches", self.path)
            if match:
                season_id = int(match.group(1))
                _json_response(self, HTTPStatus.OK, self._app().api.get_season_matches(season_id))
                return

            match = re.fullmatch(r"/api/matches/(\d+)", self.path)
            if match:
                match_id = int(match.group(1))
                _json_response(self, HTTPStatus.OK, self._app().api.get_match(match_id))
                return

            match = re.fullmatch(r"/api/matches/(\d+)/innings", self.path)
            if match:
                match_id = int(match.group(1))
                _json_response(self, HTTPStatus.OK, self._app().api.get_match_innings(match_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)", self.path)
            if match:
                session_id = match.group(1)
                _json_response(self, HTTPStatus.OK, self._app().api.get_replay(session_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)/ledger", self.path)
            if match:
                session_id = match.group(1)
                _json_response(self, HTTPStatus.OK, self._app().api.get_replay_ledger(session_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)/summary", self.path)
            if match:
                session_id = match.group(1)
                replay = self._app().api.get_replay(session_id)
                _json_response(self, HTTPStatus.OK, {"session_id": session_id, "summary": replay["summary"]})
                return

            self._serve_static()
        except ValueError as exc:
            _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not_found", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, _error_payload("internal_error", str(exc)))

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/replays":
                payload = _read_json_body(self)
                match_id = int(payload["match_id"])
                innings = int(payload["innings"])
                start_over = payload.get("start_over_number")
                start_ball = payload.get("start_ball_number")
                result = self._app().api.post_replays(
                    match_id=match_id,
                    innings=innings,
                    start_over_number=None if start_over is None else int(start_over),
                    start_ball_number=None if start_ball is None else int(start_ball),
                )
                _json_response(self, HTTPStatus.CREATED, result)
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)/predict", self.path)
            if match:
                session_id = match.group(1)
                _json_response(self, HTTPStatus.OK, self._app().api.post_replay_predict(session_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)/reveal", self.path)
            if match:
                session_id = match.group(1)
                _json_response(self, HTTPStatus.OK, self._app().api.post_replay_reveal(session_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)/restart", self.path)
            if match:
                session_id = match.group(1)
                _json_response(self, HTTPStatus.OK, self._app().api.post_replay_restart(session_id))
                return

            _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not_found", "Unknown endpoint"))
        except KeyError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload("bad_request", f"Missing required field: {exc}"))
        except json.JSONDecodeError:
            _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload("bad_request", "Invalid JSON payload"))
        except ValueError as exc:
            message = str(exc)
            status = HTTPStatus.NOT_FOUND if "not found" in message else HTTPStatus.BAD_REQUEST
            _json_response(self, status, _error_payload("invalid_request", message))
        except StopIteration as exc:
            _json_response(self, HTTPStatus.CONFLICT, _error_payload("completed", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, _error_payload("internal_error", str(exc)))

    def _serve_static(self) -> None:
        app = self._app()
        path = self.path.split("?", 1)[0]
        if path == "/":
            rel = "index.html"
        elif path in ("/app.js", "/styles.css"):
            rel = path[1:]
        else:
            _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not_found", "Unknown endpoint"))
            return

        file_path = app.static_dir / rel
        if not file_path.exists():
            _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not_found", "Static file not found"))
            return

        data = file_path.read_bytes()
        content_type = "text/html; charset=utf-8"
        if rel.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
        elif rel.endswith(".css"):
            content_type = "text/css; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def create_http_server(
    db_path: Path | str,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
) -> ThreadingHTTPServer:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    resolved_static = static_dir or (Path(__file__).resolve().parents[2] / "web")
    app = TimeMachineHttpApp(conn=conn, static_dir=resolved_static)

    class _Handler(TimeMachineRequestHandler):
        app_factory = staticmethod(lambda: app)

    server = ThreadingHTTPServer((host, port), cast(Any, _Handler))
    server.conn = conn  # type: ignore[attr-defined]
    return server

