import os

import pytest

from omi_live_football.easy_soccer import EasySoccerService
from omi_live_football.models import LookupStatus

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_SOCCER_TESTS") != "1",
    reason="Set RUN_LIVE_SOCCER_TESTS=1 to call EasySoccerData live endpoints.",
)


@pytest.mark.asyncio
async def test_known_match_can_be_loaded_from_easy_soccer_data():
    service = EasySoccerService()

    result = await service.lookup(match_id=13_511_924)

    assert result.status in {LookupStatus.FULL, LookupStatus.PARTIAL}
    assert result.match is not None
    assert result.match.match_id == 13_511_924
    assert result.match.home_team
    assert result.match.away_team
