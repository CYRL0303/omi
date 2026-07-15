"""EasySoccerData adapter and match lookup service."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from rapidfuzz import fuzz

from .config import Settings
from .models import (
    CommentaryItem,
    LookupResult,
    LookupStatus,
    MatchCandidate,
    MatchIncident,
    MatchSnapshot,
    MatchState,
    PlayerInfo,
    TeamLineup,
)

UNAVAILABLE_MESSAGE = (
    "I couldn't find reliable data for this match. It may not be covered, may not "
    "exist, or its details may currently be unavailable. Please provide the teams, "
    "date, or competition."
)


def _normalized(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "unknown")


def _name(value: Any) -> str | None:
    name = getattr(value, "name", None)
    return str(name) if name else None


class EasySoccerService:
    """Resolve queries and normalize EasySoccerData match information."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        settings: Settings | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if client is None:
            from esd import SofascoreClient

            client = SofascoreClient()
        self.client = client
        self.settings = settings or Settings.from_env()
        self.now = now or (lambda: datetime.now(UTC))

    async def lookup(
        self,
        query: str | None = None,
        *,
        date: str | None = None,
        competition: str | None = None,
        match_id: int | None = None,
    ) -> LookupResult:
        """Find a match and fetch all details available for it."""

        try:
            if match_id is not None:
                selected = await asyncio.to_thread(self.client.get_event, match_id)
            else:
                events = await asyncio.to_thread(self.client.get_events, date or "today", False)
                selected_result = self._select(events, query or "", competition)
                if isinstance(selected_result, LookupResult):
                    return selected_result
                selected = selected_result
        except Exception:
            return self._unavailable()

        return await self._snapshot(selected)

    def _select(self, events: list[Any], query: str, competition: str | None) -> Any | LookupResult:
        filtered = [
            item
            for item in events
            if not competition
            or _normalized(competition)
            in _normalized(getattr(getattr(item, "tournament", None), "name", None))
        ]
        scored: list[tuple[float, Any]] = []
        normalized_query = _normalized(query)
        for item in filtered:
            label = _normalized(f"{_name(item.home_team) or ''} {_name(item.away_team) or ''}")
            score = float(fuzz.token_set_ratio(normalized_query, label))
            if score >= 72:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        if not scored:
            return self._unavailable()
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 5:
            return LookupResult(
                status=LookupStatus.AMBIGUOUS,
                candidates=[self._candidate(item) for _, item in scored[:5]],
                message="Multiple matches fit this request. Please specify the teams, date, or competition.",
            )
        return scored[0][1]

    async def _snapshot(self, event: Any) -> LookupResult:
        popular = self._is_popular(event)
        snapshot = self._base_snapshot(event, popular)
        if not popular:
            snapshot.missing_fields = ["comments", "incidents", "lineups", "statistics"]
            return LookupResult(
                status=LookupStatus.PARTIAL,
                match=snapshot,
                message="Only partial information is currently available for this match.",
            )

        operations = {
            "lineups": self.client.get_match_lineups,
            "incidents": self.client.get_match_incidents,
            "comments": self.client.get_match_comments,
            "statistics": self.client.get_match_stats,
        }
        values: dict[str, Any] = {}
        missing: list[str] = []
        for field_name, operation in operations.items():
            try:
                values[field_name] = await asyncio.to_thread(operation, event.id)
            except Exception:
                missing.append(field_name)

        if "lineups" in values:
            snapshot.home_lineup = self._lineup(values["lineups"].home, event.home_team)
            snapshot.away_lineup = self._lineup(values["lineups"].away, event.away_team)
        if "incidents" in values:
            snapshot.incidents = [self._incident(item, event) for item in values["incidents"]]
        if "comments" in values:
            snapshot.comments = [self._comment(item) for item in values["comments"]]
        if "statistics" in values:
            snapshot.statistics = self._plain(values["statistics"])
        snapshot.missing_fields = sorted(missing)
        status = LookupStatus.PARTIAL if missing else LookupStatus.FULL
        message = self._summary(snapshot)
        if missing:
            message += f" Only partial information is currently available. Missing: {', '.join(sorted(missing))}."
        return LookupResult(status=status, match=snapshot, message=message)

    def _base_snapshot(self, event: Any, popular: bool) -> MatchSnapshot:
        home_score = getattr(getattr(event, "home_score", None), "current", None)
        away_score = getattr(getattr(event, "away_score", None), "current", None)
        timestamp = getattr(event, "start_timestamp", None)
        start_time = datetime.fromtimestamp(timestamp, UTC) if timestamp else None
        state = self._state(event)
        minute = None
        if state is MatchState.LIVE:
            try:
                minute = max(0, int(event.current_elapsed_minutes))
            except (AttributeError, TypeError, ValueError, OSError):
                minute = None
        score = None
        if home_score is not None and away_score is not None:
            score = f"{home_score}-{away_score}"
        return MatchSnapshot(
            match_id=int(event.id),
            home_team=_name(event.home_team) or "Unknown home team",
            away_team=_name(event.away_team) or "Unknown away team",
            competition=getattr(getattr(event, "tournament", None), "name", None),
            start_time=start_time,
            state=state,
            status_description=getattr(getattr(event, "status", None), "description", None),
            minute=minute,
            home_score=home_score,
            away_score=away_score,
            score=score,
            popular=popular,
            data_updated_at=self.now(),
        )

    def _state(self, event: Any) -> MatchState:
        status = _enum_value(getattr(getattr(event, "status", None), "type", None))
        description = _normalized(getattr(getattr(event, "status", None), "description", None))
        if status == "inprogress" and "half time" in description:
            return MatchState.HALFTIME
        return {
            "notstarted": MatchState.SCHEDULED,
            "inprogress": MatchState.LIVE,
            "finished": MatchState.FINISHED,
            "postponed": MatchState.POSTPONED,
            "cancelled": MatchState.CANCELLED,
        }.get(status, MatchState.UNKNOWN)

    def _is_popular(self, event: Any) -> bool:
        competition = _normalized(getattr(getattr(event, "tournament", None), "name", None))
        teams = {_normalized(_name(event.home_team)), _normalized(_name(event.away_team))}
        return competition in {
            _normalized(item) for item in self.settings.popular_competitions
        } or bool(teams & {_normalized(item) for item in self.settings.popular_teams})

    def _lineup(self, raw: Any, team: Any) -> TeamLineup:
        players = []
        for item in getattr(raw, "players", []) or []:
            info = getattr(item, "info", None)
            statistics = getattr(item, "statistics", None)
            players.append(
                (
                    bool(getattr(item, "substitute", False)),
                    PlayerInfo(
                        name=_name(info) or "Unknown player",
                        position=getattr(info, "position", None),
                        jersey_number=getattr(info, "jersey_number", None),
                        rating=getattr(statistics, "rating", None),
                    ),
                )
            )
        starters = [player for substitute, player in players if not substitute]
        substitutes = [player for substitute, player in players if substitute]
        coach = self._staff_name(getattr(raw, "support_staff", None))
        if not coach:
            coach = _name(getattr(team, "manager", None))
        return TeamLineup(
            formation=getattr(raw, "formation", None) or None,
            starters=starters,
            substitutes=substitutes,
            current_players=list(starters),
            coach=coach,
        )

    @staticmethod
    def _staff_name(staff: Any) -> str | None:
        for item in staff or []:
            if isinstance(item, dict) and item.get("name"):
                return str(item["name"])
            if _name(item):
                return _name(item)
        return None

    def _incident(self, item: Any, event: Any) -> MatchIncident:
        incident_type = _enum_value(getattr(item, "type", None))
        team = _name(event.home_team) if getattr(item, "is_home", False) else _name(event.away_team)
        parts = (
            event.id,
            getattr(item, "time", None),
            incident_type,
            getattr(item, "text", None),
            _name(getattr(item, "player", None)),
        )
        return MatchIncident(
            key=hashlib.sha256(repr(parts).encode()).hexdigest(),
            minute=getattr(item, "time", None),
            added_time=getattr(item, "added_time", None),
            type=incident_type,
            text=getattr(item, "text", None),
            team=team,
            player=_name(getattr(item, "player", None)),
            player_in=_name(getattr(item, "player_in", None)),
            player_out=_name(getattr(item, "player_out", None)),
            home_score=getattr(item, "home_score", None),
            away_score=getattr(item, "away_score", None),
        )

    @staticmethod
    def _comment(item: Any) -> CommentaryItem:
        comment_type = _enum_value(getattr(item, "type", None))
        parts = (
            getattr(item, "period", None),
            getattr(item, "time", None),
            comment_type,
            getattr(item, "text", None),
        )
        return CommentaryItem(
            key=hashlib.sha256(repr(parts).encode()).hexdigest(),
            minute=getattr(item, "time", None),
            period=getattr(item, "period", None),
            type=comment_type,
            text=str(getattr(item, "text", "") or ""),
        )

    @staticmethod
    def _plain(value: Any) -> dict[str, Any]:
        if dataclasses.is_dataclass(value):
            return dataclasses.asdict(value)
        if isinstance(value, dict):
            return value
        return {"available": True}

    def _candidate(self, event: Any) -> MatchCandidate:
        timestamp = getattr(event, "start_timestamp", None)
        return MatchCandidate(
            match_id=int(event.id),
            home_team=_name(event.home_team) or "Unknown home team",
            away_team=_name(event.away_team) or "Unknown away team",
            competition=getattr(getattr(event, "tournament", None), "name", None),
            start_time=datetime.fromtimestamp(timestamp, UTC) if timestamp else None,
        )

    @staticmethod
    def _summary(snapshot: MatchSnapshot) -> str:
        score = snapshot.score or "score unavailable"
        return (
            f"{snapshot.home_team} {score} {snapshot.away_team}. "
            f"Status: {snapshot.status_description or snapshot.state.value}."
        )

    @staticmethod
    def _unavailable() -> LookupResult:
        return LookupResult(
            status=LookupStatus.UNAVAILABLE_OR_NOT_FOUND,
            message=UNAVAILABLE_MESSAGE,
        )
