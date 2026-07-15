"""The single Omi football match tool."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel

from .models import LookupStatus, MatchSnapshot, MatchState


class ToolAction(StrEnum):
    QUERY = "query"
    START_COMMENTARY = "start_commentary"
    STOP_COMMENTARY = "stop_commentary"


class ToolRequest(BaseModel):
    uid: str
    app_id: str
    tool_name: str
    action: ToolAction
    match_query: str | None = None
    match_id: int | None = None
    date: str | None = None
    competition: str | None = None


class SoccerLookup(Protocol):
    async def lookup(
        self,
        query: str | None = None,
        *,
        date: str | None = None,
        competition: str | None = None,
        match_id: int | None = None,
    ): ...


class CommentaryControl(Protocol):
    async def start(self, uid: str, match: MatchSnapshot) -> bool: ...

    async def stop(self, uid: str) -> bool: ...


class FootballTool:
    """Route all Omi football actions through one tool contract."""

    def __init__(self, *, soccer: SoccerLookup, commentary: CommentaryControl) -> None:
        self.soccer = soccer
        self.commentary = commentary

    async def handle(self, request: ToolRequest) -> dict[str, str]:
        if request.tool_name != "football_match":
            return {"error": "The requested tool name is invalid."}

        if request.action is ToolAction.STOP_COMMENTARY:
            stopped = await self.commentary.stop(request.uid)
            if stopped:
                return {"result": "Live commentary stopped."}
            return {"result": "No live commentary session was active."}

        if not request.match_query and request.match_id is None:
            return {
                "error": (
                    "Provide a match query or match ID before requesting match information."
                )
            }

        result = await self.soccer.lookup(
            request.match_query,
            date=request.date,
            competition=request.competition,
            match_id=request.match_id,
        )
        if request.action is ToolAction.QUERY:
            return {"result": result.message}

        if result.status in {
            LookupStatus.AMBIGUOUS,
            LookupStatus.UNAVAILABLE_OR_NOT_FOUND,
        } or result.match is None:
            return {"result": result.message}

        match = result.match
        if not match.popular:
            return {
                "result": (
                    "Only partial information is available for this match, so continuous "
                    "live commentary is not supported."
                )
            }
        if match.state not in {
            MatchState.SCHEDULED,
            MatchState.LIVE,
            MatchState.HALFTIME,
        }:
            return {
                "result": (
                    "Live commentary cannot start because this match is not scheduled or live."
                )
            }

        started = await self.commentary.start(request.uid, match)
        if not started:
            return {"result": "Live commentary is already active for this match."}
        return {
            "result": (
                f"Live commentary started for {match.home_team} vs {match.away_team}."
            )
        }

