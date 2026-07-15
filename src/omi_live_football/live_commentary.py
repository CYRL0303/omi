"""Per-user in-memory live commentary polling."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Settings
from .models import MatchIncident, MatchSnapshot, MatchState


class SoccerLookup(Protocol):
    async def lookup(
        self,
        query: str | None = None,
        *,
        date: str | None = None,
        competition: str | None = None,
        match_id: int | None = None,
    ): ...


class Notifier(Protocol):
    async def send(self, uid: str, message: str) -> None: ...


@dataclass(slots=True)
class CommentarySession:
    uid: str
    match: MatchSnapshot
    seen: set[str] = field(default_factory=set)
    task: Any = None


class LiveCommentaryManager:
    """Manage one independently polled commentary session per Omi user."""

    def __init__(
        self,
        *,
        soccer: SoccerLookup,
        notifier: Notifier,
        settings: Settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        task_factory: Callable[[Coroutine[Any, Any, None]], Any] = asyncio.create_task,
    ) -> None:
        self.soccer = soccer
        self.notifier = notifier
        self.settings = settings
        self.sleep = sleep
        self.task_factory = task_factory
        self._sessions: dict[str, CommentarySession] = {}

    async def start(self, uid: str, match: MatchSnapshot) -> bool:
        """Start a user's commentary loop, returning false if it already exists."""

        existing = self._sessions.get(uid)
        if existing and existing.match.match_id == match.match_id:
            return False
        if existing:
            await self.stop(uid)

        seen = {item.key for item in match.comments}
        seen.update(item.key for item in match.incidents)
        session = CommentarySession(uid=uid, match=match, seen=seen)
        self._sessions[uid] = session
        session.task = self.task_factory(self._run(uid))
        return True

    async def stop(self, uid: str) -> bool:
        """Stop one user's commentary loop."""

        session = self._sessions.pop(uid, None)
        if session is None:
            return False
        if session.task is not None and not session.task.done():
            session.task.cancel()
            with suppress(asyncio.CancelledError):
                await session.task
        return True

    def is_active(self, uid: str) -> bool:
        """Return whether the user currently has a commentary session."""

        return uid in self._sessions

    async def poll_once(self, uid: str) -> bool:
        """Poll one user session once and return whether it should continue."""

        session = self._sessions.get(uid)
        if session is None:
            return False
        result = await self.soccer.lookup(match_id=session.match.match_id)
        if result.match is None:
            return True

        updated = result.match
        if "comments" not in updated.missing_fields:
            for item in updated.comments:
                if item.key not in session.seen:
                    await self.notifier.send(uid, self._comment_message(item.minute, item.text))
                    session.seen.add(item.key)
        else:
            for item in updated.incidents:
                if item.key not in session.seen:
                    message = self._incident_message(item)
                    if message:
                        await self.notifier.send(uid, message)
                    session.seen.add(item.key)

        session.match = updated
        if updated.state is MatchState.FINISHED:
            if "__fulltime__" not in session.seen:
                await self.notifier.send(uid, self._fulltime_message(updated))
                session.seen.add("__fulltime__")
            return False
        if updated.state in {MatchState.CANCELLED, MatchState.POSTPONED}:
            await self.notifier.send(
                uid,
                f"Live commentary stopped because the match is {updated.state.value}.",
            )
            return False
        return True

    async def close(self) -> None:
        """Cancel all in-memory sessions during application shutdown."""

        for uid in list(self._sessions):
            await self.stop(uid)

    async def _run(self, uid: str) -> None:
        try:
            while await self.poll_once(uid):
                session = self._sessions.get(uid)
                if session is None:
                    return
                delay = (
                    self.settings.live_poll_seconds
                    if session.match.state is MatchState.LIVE
                    else self.settings.idle_poll_seconds
                )
                await self.sleep(delay)
        finally:
            self._sessions.pop(uid, None)

    @staticmethod
    def _comment_message(minute: int | None, text: str) -> str:
        return f"{minute}' {text}" if minute is not None else text

    @staticmethod
    def _incident_message(item: MatchIncident) -> str | None:
        minute = f" in the {item.minute}th minute" if item.minute is not None else ""
        team = item.team or "a team"
        if item.type == "goal":
            return f"Goal for {team}{minute}."
        if item.type == "card":
            player = f" for {item.player}" if item.player else ""
            return f"Card{player}, {team}{minute}."
        if item.type == "substitution":
            players = ""
            if item.player_in or item.player_out:
                players = f": {item.player_in or 'unknown'} replaces {item.player_out or 'unknown'}"
            return f"Substitution for {team}{players}{minute}."
        if item.type == "varDecision":
            return f"VAR decision involving {team}{minute}."
        if item.type == "period":
            return item.text or f"Match period update{minute}."
        return None

    @staticmethod
    def _fulltime_message(match: MatchSnapshot) -> str:
        score = match.score or "score unavailable"
        return f"Full time: {match.home_team} {score} {match.away_team}."
