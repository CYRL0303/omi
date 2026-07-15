from datetime import UTC, datetime

import pytest

from omi_live_football.football_tool import FootballTool, ToolRequest
from omi_live_football.models import (
    LookupResult,
    LookupStatus,
    MatchSnapshot,
    MatchState,
)


def snapshot(*, popular=True, state=MatchState.LIVE):
    return MatchSnapshot(
        match_id=42,
        home_team="Real Madrid",
        away_team="Arsenal",
        competition="UEFA Champions League",
        state=state,
        home_score=2,
        away_score=1,
        score="2-1",
        popular=popular,
        missing_fields=[] if popular else ["comments", "lineups"],
        data_updated_at=datetime(2026, 7, 15, tzinfo=UTC),
    )


class FakeSoccerService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def lookup(self, query=None, *, date=None, competition=None, match_id=None):
        self.calls.append(
            {
                "query": query,
                "date": date,
                "competition": competition,
                "match_id": match_id,
            }
        )
        return self.result


class FakeCommentaryManager:
    def __init__(self, *, started=True, stopped=True):
        self.started = started
        self.stopped = stopped
        self.start_calls = []
        self.stop_calls = []

    async def start(self, uid, match):
        self.start_calls.append((uid, match.match_id))
        return self.started

    async def stop(self, uid):
        self.stop_calls.append(uid)
        return self.stopped


def request(action, **values):
    return ToolRequest(
        uid="user-1",
        app_id="app-1",
        tool_name="football_match",
        action=action,
        **values,
    )


@pytest.mark.asyncio
async def test_query_returns_lookup_message():
    result = LookupResult(
        status=LookupStatus.FULL,
        match=snapshot(),
        message="Real Madrid 2-1 Arsenal. Status: Second half.",
    )
    soccer = FakeSoccerService(result)
    tool = FootballTool(soccer=soccer, commentary=FakeCommentaryManager())

    response = await tool.handle(request("query", match_query="Real Madrid Arsenal"))

    assert response == {"result": result.message}
    assert soccer.calls[0]["query"] == "Real Madrid Arsenal"


@pytest.mark.asyncio
async def test_query_returns_neutral_unavailable_message():
    result = LookupResult(
        status=LookupStatus.UNAVAILABLE_OR_NOT_FOUND,
        message="Match coverage is unavailable.",
    )
    tool = FootballTool(soccer=FakeSoccerService(result), commentary=FakeCommentaryManager())

    response = await tool.handle(request("query", match_query="Unknown FC"))

    assert response == {"result": "Match coverage is unavailable."}


@pytest.mark.asyncio
async def test_start_commentary_creates_user_session():
    result = LookupResult(
        status=LookupStatus.FULL,
        match=snapshot(),
        message="Match found.",
    )
    manager = FakeCommentaryManager()
    tool = FootballTool(soccer=FakeSoccerService(result), commentary=manager)

    response = await tool.handle(request("start_commentary", match_query="Real Madrid Arsenal"))

    assert response == {"result": "Live commentary started for Real Madrid vs Arsenal."}
    assert manager.start_calls == [("user-1", 42)]


@pytest.mark.asyncio
async def test_repeated_start_is_idempotent():
    result = LookupResult(
        status=LookupStatus.FULL,
        match=snapshot(),
        message="Match found.",
    )
    tool = FootballTool(
        soccer=FakeSoccerService(result),
        commentary=FakeCommentaryManager(started=False),
    )

    response = await tool.handle(request("start_commentary", match_query="Real Madrid Arsenal"))

    assert response == {"result": "Live commentary is already active for this match."}


@pytest.mark.asyncio
async def test_non_popular_match_rejects_continuous_commentary():
    result = LookupResult(
        status=LookupStatus.PARTIAL,
        match=snapshot(popular=False),
        message="Partial match information.",
    )
    manager = FakeCommentaryManager()
    tool = FootballTool(soccer=FakeSoccerService(result), commentary=manager)

    response = await tool.handle(request("start_commentary", match_query="Local Town Village FC"))

    assert response == {
        "result": (
            "Only partial information is available for this match, so continuous "
            "live commentary is not supported."
        )
    }
    assert manager.start_calls == []


@pytest.mark.asyncio
async def test_stop_commentary_cancels_user_session():
    manager = FakeCommentaryManager()
    tool = FootballTool(
        soccer=FakeSoccerService(None),
        commentary=manager,
    )

    response = await tool.handle(request("stop_commentary"))

    assert response == {"result": "Live commentary stopped."}
    assert manager.stop_calls == ["user-1"]


@pytest.mark.asyncio
async def test_stop_without_session_is_harmless():
    tool = FootballTool(
        soccer=FakeSoccerService(None),
        commentary=FakeCommentaryManager(stopped=False),
    )

    response = await tool.handle(request("stop_commentary"))

    assert response == {"result": "No live commentary session was active."}


@pytest.mark.asyncio
async def test_query_requires_match_reference():
    tool = FootballTool(soccer=FakeSoccerService(None), commentary=FakeCommentaryManager())

    response = await tool.handle(request("query"))

    assert response == {
        "error": "Provide a match query or match ID before requesting match information."
    }
