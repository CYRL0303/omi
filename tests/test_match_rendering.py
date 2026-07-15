from datetime import UTC, datetime

from omi_live_football.easy_soccer import EasySoccerService, apply_substitutions
from omi_live_football.models import (
    CommentaryItem,
    MatchIncident,
    MatchSnapshot,
    MatchState,
    PlayerInfo,
    TeamLineup,
)


def detailed_match():
    home_starter = PlayerInfo(name="Home Starter", position="M", jersey_number="8")
    home_bench = PlayerInfo(name="Home Substitute", position="F", jersey_number="19")
    away_starter = PlayerInfo(name="Away Starter", position="D", jersey_number="4")
    return MatchSnapshot(
        match_id=42,
        home_team="Real Madrid",
        away_team="Arsenal",
        competition="UEFA Champions League",
        state=MatchState.LIVE,
        status_description="Second half",
        minute=67,
        home_score=2,
        away_score=1,
        score="2-1",
        popular=True,
        home_lineup=TeamLineup(
            formation="4-3-3",
            starters=[home_starter],
            substitutes=[home_bench],
            current_players=[home_starter],
            coach="Home Coach",
        ),
        away_lineup=TeamLineup(
            formation="4-2-3-1",
            starters=[away_starter],
            current_players=[away_starter],
            coach="Away Coach",
        ),
        incidents=[
            MatchIncident(
                key="goal-1",
                minute=65,
                type="goal",
                text="Goal",
                team="Real Madrid",
                player="Home Starter",
                home_score=2,
                away_score=1,
            )
        ],
        comments=[
            CommentaryItem(
                key="comment-1",
                minute=65,
                period="Second half",
                type="scoreChange",
                text="Goal!",
            )
        ],
        statistics={"available": True},
        data_updated_at=datetime(2026, 7, 15, 1, 30, tzinfo=UTC),
    )


def test_match_summary_exposes_details_to_omi():
    summary = EasySoccerService._summary(detailed_match())

    assert "Competition: UEFA Champions League." in summary
    assert "Minute: 67." in summary
    assert "Real Madrid formation: 4-3-3." in summary
    assert "Current players: Home Starter." in summary
    assert "Coach: Home Coach." in summary
    assert "Recent incidents: 65' Goal (Home Starter)." in summary
    assert "Recent commentary: 65' Goal!" in summary
    assert "Statistics: available." in summary
    assert "Updated: 2026-07-15T01:30:00+00:00." in summary


def test_substitution_updates_current_players():
    snapshot = detailed_match()
    snapshot.incidents.append(
        MatchIncident(
            key="sub-1",
            minute=70,
            type="substitution",
            team="Real Madrid",
            player_in="Home Substitute",
            player_out="Home Starter",
        )
    )

    apply_substitutions(snapshot)

    assert [player.name for player in snapshot.home_lineup.current_players] == ["Home Substitute"]
