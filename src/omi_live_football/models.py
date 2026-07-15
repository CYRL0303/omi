"""Normalized models used by the football tool."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MatchState(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    HALFTIME = "halftime"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class LookupStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE_OR_NOT_FOUND = "unavailable_or_not_found"


class PlayerInfo(BaseModel):
    name: str
    position: str | None = None
    jersey_number: str | None = None
    rating: float | None = None


class TeamLineup(BaseModel):
    formation: str | None = None
    starters: list[PlayerInfo] = Field(default_factory=list)
    substitutes: list[PlayerInfo] = Field(default_factory=list)
    current_players: list[PlayerInfo] = Field(default_factory=list)
    coach: str | None = None


class MatchIncident(BaseModel):
    key: str
    minute: int | None = None
    added_time: int | None = None
    type: str
    text: str | None = None
    team: str | None = None
    player: str | None = None
    player_in: str | None = None
    player_out: str | None = None
    home_score: int | None = None
    away_score: int | None = None


class CommentaryItem(BaseModel):
    key: str
    minute: int | None = None
    period: str | None = None
    type: str
    text: str


class MatchSnapshot(BaseModel):
    match_id: int
    home_team: str
    away_team: str
    competition: str | None = None
    start_time: datetime | None = None
    state: MatchState = MatchState.UNKNOWN
    status_description: str | None = None
    minute: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    score: str | None = None
    popular: bool = False
    home_lineup: TeamLineup | None = None
    away_lineup: TeamLineup | None = None
    incidents: list[MatchIncident] = Field(default_factory=list)
    comments: list[CommentaryItem] = Field(default_factory=list)
    statistics: dict[str, Any] | None = None
    missing_fields: list[str] = Field(default_factory=list)
    data_updated_at: datetime


class MatchCandidate(BaseModel):
    match_id: int
    home_team: str
    away_team: str
    competition: str | None = None
    start_time: datetime | None = None


class LookupResult(BaseModel):
    status: LookupStatus
    match: MatchSnapshot | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)
    message: str
