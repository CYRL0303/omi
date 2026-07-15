from types import SimpleNamespace

import pytest

from omi_live_football.config import Settings
from omi_live_football.easy_soccer import EasySoccerService
from omi_live_football.models import LookupStatus


def ns(**values):
    return SimpleNamespace(**values)


def live_event():
    return ns(
        id=99,
        home_team=ns(name="Real Madrid", manager=ns(name="Home Coach")),
        away_team=ns(name="Arsenal", manager=ns(name="Away Coach")),
        home_score=ns(current=1),
        away_score=ns(current=0),
        tournament=ns(name="UEFA Champions League"),
        status=ns(type=ns(value="inprogress"), description="First half"),
        start_timestamp=1_752_508_800,
        current_elapsed_minutes=25,
    )


class LiveOnlyClient:
    def get_events(self, date="today", live=False):
        if live:
            return [live_event()]
        raise RuntimeError("scheduled endpoint unavailable")

    def get_match_lineups(self, event_id):
        raise RuntimeError("lineups unavailable")

    def get_match_incidents(self, event_id):
        return []

    def get_match_comments(self, event_id):
        return []

    def get_match_stats(self, event_id):
        raise RuntimeError("statistics unavailable")


@pytest.mark.asyncio
async def test_today_query_uses_live_events_when_schedule_is_unavailable():
    service = EasySoccerService(
        client=LiveOnlyClient(),
        settings=Settings(popular_competitions=("UEFA Champions League",)),
    )

    result = await service.lookup("Real Madrid Arsenal")

    assert result.status is LookupStatus.PARTIAL
    assert result.match is not None
    assert result.match.match_id == 99
    assert result.match.score == "1-0"
