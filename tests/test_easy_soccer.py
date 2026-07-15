from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from omi_live_football.config import Settings
from omi_live_football.easy_soccer import EasySoccerService
from omi_live_football.models import LookupStatus, MatchState


def ns(**values):
    return SimpleNamespace(**values)


def event(
    event_id: int,
    home: str,
    away: str,
    *,
    competition: str = "UEFA Champions League",
    status_type: str = "inprogress",
):
    return ns(
        id=event_id,
        home_team=ns(name=home, manager=ns(name=f"{home} Coach")),
        away_team=ns(name=away, manager=ns(name=f"{away} Coach")),
        home_score=ns(current=2),
        away_score=ns(current=1),
        tournament=ns(name=competition),
        status=ns(type=ns(value=status_type), description="Second half"),
        start_timestamp=1_752_508_800,
        current_elapsed_minutes=67,
    )


class FakeClient:
    def __init__(self, events, *, missing=(), list_error=None):
        self.events = events
        self.missing = set(missing)
        self.list_error = list_error

    def get_events(self, date="today", live=False):
        if self.list_error:
            raise self.list_error
        return self.events

    def get_event(self, event_id):
        return next(item for item in self.events if item.id == event_id)

    def get_match_lineups(self, event_id):
        if "lineups" in self.missing:
            raise RuntimeError("lineups unavailable")

        def player(name, substitute=False):
            return ns(
                info=ns(name=name, position="M", jersey_number="8"),
                substitute=substitute,
                statistics=ns(rating=7.2),
            )

        return ns(
            home=ns(
                formation="4-3-3",
                players=[player("Home Starter"), player("Home Bench", True)],
                support_staff=[{"name": "Home Coach"}],
            ),
            away=ns(
                formation="4-2-3-1",
                players=[player("Away Starter"), player("Away Bench", True)],
                support_staff=[{"name": "Away Coach"}],
            ),
        )

    def get_match_incidents(self, event_id):
        if "incidents" in self.missing:
            raise RuntimeError("incidents unavailable")
        return [
            ns(
                time=65,
                added_time=None,
                type=ns(value="goal"),
                text="Goal",
                is_home=True,
                home_score=2,
                away_score=1,
                player=ns(name="Home Starter"),
                player_in=ns(name=None),
                player_out=ns(name=None),
                details="regular",
            )
        ]

    def get_match_comments(self, event_id):
        if "comments" in self.missing:
            raise RuntimeError("comments unavailable")
        return [ns(time=65, period="2", type=ns(value="scoreChange"), text="Goal!")]

    def get_match_stats(self, event_id):
        if "statistics" in self.missing:
            raise RuntimeError("statistics unavailable")
        return ns(all=ns(match_overview=ns()))


def settings():
    return Settings(
        popular_competitions=("UEFA Champions League",),
        popular_teams=("Real Madrid", "Arsenal"),
    )


@pytest.mark.asyncio
async def test_exact_popular_match_returns_complete_snapshot():
    service = EasySoccerService(
        client=FakeClient([event(10, "Real Madrid", "Arsenal")]),
        settings=settings(),
        now=lambda: datetime(2026, 7, 15, tzinfo=UTC),
    )

    result = await service.lookup("Real Madrid vs Arsenal", date="2026-07-15")

    assert result.status is LookupStatus.FULL
    assert result.match.match_id == 10
    assert result.match.state is MatchState.LIVE
    assert result.match.score == "2-1"
    assert result.match.home_lineup.formation == "4-3-3"
    assert result.match.home_lineup.starters[0].name == "Home Starter"
    assert result.match.comments[0].text == "Goal!"
    assert result.match.missing_fields == []


@pytest.mark.asyncio
async def test_misspelled_team_names_still_resolve():
    service = EasySoccerService(
        client=FakeClient([event(10, "Real Madrid", "Arsenal")]),
        settings=settings(),
    )

    result = await service.lookup("Real Madird Arsnal", date="2026-07-15")

    assert result.match.match_id == 10


@pytest.mark.asyncio
async def test_ambiguous_query_returns_candidates():
    service = EasySoccerService(
        client=FakeClient(
            [
                event(10, "Arsenal", "Chelsea"),
                event(11, "Arsenal Women", "Chelsea Women"),
            ]
        ),
        settings=settings(),
    )

    result = await service.lookup("Arsenal Chelsea", date="2026-07-15")

    assert result.status is LookupStatus.AMBIGUOUS
    assert [candidate.match_id for candidate in result.candidates] == [10, 11]


@pytest.mark.asyncio
async def test_missing_optional_details_returns_partial_base_result():
    service = EasySoccerService(
        client=FakeClient(
            [event(10, "Real Madrid", "Arsenal")],
            missing={"lineups", "comments"},
        ),
        settings=settings(),
    )

    result = await service.lookup("Real Madrid Arsenal", date="2026-07-15")

    assert result.status is LookupStatus.PARTIAL
    assert result.match.score == "2-1"
    assert result.match.missing_fields == ["comments", "lineups"]


@pytest.mark.asyncio
async def test_non_popular_match_returns_partial_without_detail_requests():
    client = FakeClient([event(20, "Local Town", "Village FC", competition="Regional League")])
    service = EasySoccerService(client=client, settings=settings())

    result = await service.lookup("Local Town Village", date="2026-07-15")

    assert result.status is LookupStatus.PARTIAL
    assert result.match.popular is False
    assert result.match.missing_fields == ["comments", "incidents", "lineups", "statistics"]


@pytest.mark.asyncio
async def test_empty_provider_result_uses_neutral_unavailable_message():
    service = EasySoccerService(client=FakeClient([]), settings=settings())

    result = await service.lookup("Unknown FC", date="2026-07-15")

    assert result.status is LookupStatus.UNAVAILABLE_OR_NOT_FOUND
    assert result.message == (
        "I couldn't find reliable data for this match. It may not be covered, may not "
        "exist, or its details may currently be unavailable. Please provide the teams, "
        "date, or competition."
    )


@pytest.mark.asyncio
async def test_provider_failure_does_not_claim_match_does_not_exist():
    service = EasySoccerService(
        client=FakeClient([], list_error=TimeoutError("provider timeout")),
        settings=settings(),
    )

    result = await service.lookup("Unknown FC", date="2026-07-15")

    assert result.status is LookupStatus.UNAVAILABLE_OR_NOT_FOUND
    assert "may not exist" in result.message
    assert "does not exist" not in result.message
