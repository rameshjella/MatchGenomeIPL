from __future__ import annotations

from typing import Any

from .time_machine import TimeMachineService


class TimeMachineAPI:
    """Framework-free API facade for the Time Machine vertical slice."""

    def __init__(self, service: TimeMachineService) -> None:
        self.service = service

    def get_seasons(self) -> dict[str, Any]:
        return {"seasons": self.service.list_seasons()}

    def get_season_matches(self, season_id: int) -> dict[str, Any]:
        return {"season_id": season_id, "matches": self.service.list_matches(season_id)}

    def get_match(self, match_id: int) -> dict[str, Any]:
        return self.service.get_match(match_id)

    def get_match_innings(self, match_id: int) -> dict[str, Any]:
        return {"match_id": match_id, "innings": self.service.list_innings(match_id)}

    def post_replays(
        self,
        match_id: int,
        innings: int,
        model_version: str | None = None,
        start_over_number: int | None = None,
        start_ball_number: int | None = None,
    ) -> dict[str, Any]:
        return self.service.create_replay_session(
            match_id=match_id,
            innings=innings,
            model_version=model_version or self.service.DEFAULT_MODEL_VERSION,
            start_over_number=start_over_number,
            start_ball_number=start_ball_number,
        )

    def get_replay(self, session_id: str) -> dict[str, Any]:
        return self.service.inspect_replay_session(session_id)

    def post_replay_predict(self, session_id: str) -> dict[str, Any]:
        return self.service.predict_next(session_id)

    def post_replay_reveal(self, session_id: str) -> dict[str, Any]:
        return self.service.reveal_next(session_id)

    def post_replay_restart(self, session_id: str) -> dict[str, Any]:
        return self.service.restart_replay_session(session_id)

    def get_replay_ledger(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "entries": self.service.replay_ledger(session_id)}

    def get_players(self, query: str = "", limit: int = 50) -> dict[str, Any]:
        return {
            "query": query,
            "limit": limit,
            "players": self.service.list_players(query=query, limit=limit),
        }

    def get_player(self, player_name: str, session_id: str | None = None) -> dict[str, Any]:
        return self.service.get_player(player_name, session_id=session_id)

    def post_ask(self, question: str) -> dict[str, Any]:
        return self.service.ask(question)

