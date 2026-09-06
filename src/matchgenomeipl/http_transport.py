from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, cast
from urllib.parse import parse_qs, unquote, urlparse

from .runtime_logging import log_event, log_http
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
        started = time.perf_counter()
        status_code = HTTPStatus.OK
        try:
            parsed = urlparse(self.path)
            route = parsed.path
            query = parse_qs(parsed.query)

            if route == "/api/seasons":
                _json_response(self, HTTPStatus.OK, self._app().api.get_seasons())
                return

            match = re.fullmatch(r"/api/seasons/(\d+)/matches", route)
            if match:
                season_id = int(match.group(1))
                _json_response(self, HTTPStatus.OK, self._app().api.get_season_matches(season_id))
                return

            match = re.fullmatch(r"/api/matches/(\d+)", route)
            if match:
                match_id = int(match.group(1))
                _json_response(self, HTTPStatus.OK, self._app().api.get_match(match_id))
                return

            match = re.fullmatch(r"/api/matches/(\d+)/innings", route)
            if match:
                match_id = int(match.group(1))
                _json_response(self, HTTPStatus.OK, self._app().api.get_match_innings(match_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)", route)
            if match:
                session_id = match.group(1)
                _json_response(self, HTTPStatus.OK, self._app().api.get_replay(session_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)/ledger", route)
            if match:
                session_id = match.group(1)
                _json_response(self, HTTPStatus.OK, self._app().api.get_replay_ledger(session_id))
                return

            match = re.fullmatch(r"/api/replays/([0-9a-f\-]+)/summary", route)
            if match:
                session_id = match.group(1)
                replay = self._app().api.get_replay(session_id)
                _json_response(self, HTTPStatus.OK, {"session_id": session_id, "summary": replay["summary"]})
                return

            if route == "/api/players":
                search = str(query.get("query", [""])[0])
                limit = int(query.get("limit", [50])[0])
                _json_response(self, HTTPStatus.OK, self._app().api.get_players(query=search, limit=limit))
                return

            match = re.fullmatch(r"/api/players/(.+)", route)
            if match:
                player_name = unquote(match.group(1))
                _json_response(self, HTTPStatus.OK, self._app().api.get_player(player_name))
                return

            status_code = self._serve_static()
        except ValueError as exc:
            status_code = HTTPStatus.NOT_FOUND
            _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not_found", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, _error_payload("internal_error", str(exc)))
        finally:
            log_http("GET", self.path, int(status_code), started)

    def do_POST(self) -> None:  # noqa: N802
        started = time.perf_counter()
        status_code = HTTPStatus.OK
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
                status_code = HTTPStatus.CREATED
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
            status_code = HTTPStatus.BAD_REQUEST
            _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload("bad_request", f"Missing required field: {exc}"))
        except json.JSONDecodeError:
            status_code = HTTPStatus.BAD_REQUEST
            _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload("bad_request", "Invalid JSON payload"))
        except ValueError as exc:
            message = str(exc)
            status = HTTPStatus.NOT_FOUND if "not found" in message else HTTPStatus.BAD_REQUEST
            status_code = status
            _json_response(self, status, _error_payload("invalid_request", message))
        except StopIteration as exc:
            status_code = HTTPStatus.CONFLICT
            _json_response(self, HTTPStatus.CONFLICT, _error_payload("completed", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, _error_payload("internal_error", str(exc)))
        finally:
            log_http("POST", self.path, int(status_code), started)

    def _serve_static(self) -> int:
        app = self._app()
        path = self.path.split("?", 1)[0]
        if path == "/":
            rel = "index.html"
        elif path in ("/app.js", "/styles.css", "/player_photos.json"):
            rel = path[1:]
        else:
            _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not_found", "Unknown endpoint"))
            return int(HTTPStatus.NOT_FOUND)

        file_path = app.static_dir / rel
        if not file_path.exists():
            _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not_found", "Static file not found"))
            return int(HTTPStatus.NOT_FOUND)

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
        return int(HTTPStatus.OK)


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
    log_event("SERVER", "Creating HTTP server", host=host, port=port, db_path=db_path, static_dir=resolved_static)
    app = TimeMachineHttpApp(conn=conn, static_dir=resolved_static)

    class _Handler(TimeMachineRequestHandler):
        app_factory = staticmethod(lambda: app)

    server = ThreadingHTTPServer((host, port), cast(Any, _Handler))
    server.conn = conn  # type: ignore[attr-defined]
    return server

