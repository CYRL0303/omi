from datetime import UTC, datetime

import pytest

from omi_live_football.config import Settings
from omi_live_football.live_commentary import LiveCommentaryManager
from omi_live_football.models import (
    CommentaryItem,
    LookupResult,
    LookupStatus,
    MatchIncident,
    MatchSnapshot,
    MatchState,
)


def match(*, state=MatchState.LIVE, comments=None, incidents=None):
    return MatchSnapshot(
        match_id=42,
        home_team="Real Madrid",
        away_team="Arsenal",
        competition="UEFA Champions League",
        state=state,
        home_score=2,
        away_score=1,
        score="2-1",
        popular=True,
        comments=comments or [],
        incidents=incidents or [],
        data_updated_at=datetime(2026, 7, 15, tzinfo=UTC),
    )


def comment(key="comment-1", text="Goal!", minute=65):
    return CommentaryItem(
        key=key,
        minute=minute,
        period="Second half",
        type="scoreChange",
        text=text,
    )


def incident(key="incident-1", kind="goal", minute=65):
    return MatchIncident(
        key=key,
        minute=minute,
        type=kind,
        team="Real Madrid",
        player="Home Starter",
        home_score=2,
        away_score=1,
    )


class FakeSoccer:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = []

    async def lookup(self, query=None, *, date=None, competition=None, match_id=None):
        self.calls.append(match_id)
        snapshot = self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
        status = LookupStatus.FULL if not snapshot.missing_fields else LookupStatus.PARTIAL
        return LookupResult(status=status, match=snapshot, message="Match update.")


class FakeNotifier:
    def __init__(self):
        self.messages = []

    async def send(self, uid, message):
        self.messages.append((uid, message))


class DummyTask:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def done(self):
        return self.cancelled

    def __await__(self):
        async def complete():
            return None

        return complete().__await__()


def no_run_task(coroutine):
    coroutine.close()
    return DummyTask()


def manager(snapshots):
    notifier = FakeNotifier()
    instance = LiveCommentaryManager(
        soccer=FakeSoccer(snapshots),
        notifier=notifier,
        settings=Settings(live_poll_seconds=0.01, idle_poll_seconds=0.01),
        task_factory=no_run_task,
    )
    return instance, notifier


@pytest.mark.asyncio
async def test_existing_comment_is_baseline_and_not_forwarded():
    initial = match(comments=[comment()])
    instance, notifier = manager([initial])
    await instance.start("user-1", initial)

    keep_running = await instance.poll_once("user-1")

    assert keep_running is True
    assert notifier.messages == []


@pytest.mark.asyncio
async def test_new_comment_is_forwarded_once():
    initial = match()
    updated = match(comments=[comment()])
    instance, notifier = manager([updated])
    await instance.start("user-1", initial)

    await instance.poll_once("user-1")
    await instance.poll_once("user-1")

    assert notifier.messages == [("user-1", "65' Goal!")]


@pytest.mark.asyncio
async def test_incident_is_used_when_comments_are_unavailable():
    initial = match()
    updated = match(incidents=[incident()])
    updated.missing_fields = ["comments"]
    instance, notifier = manager([updated])
    await instance.start("user-1", initial)

    await instance.poll_once("user-1")

    assert notifier.messages == [("user-1", "Goal for Real Madrid in the 65th minute.")]


@pytest.mark.asyncio
async def test_finished_match_sends_final_message_and_stops():
    initial = match()
    finished = match(state=MatchState.FINISHED)
    instance, notifier = manager([finished])
    await instance.start("user-1", initial)

    keep_running = await instance.poll_once("user-1")

    assert keep_running is False
    assert notifier.messages == [("user-1", "Full time: Real Madrid 2-1 Arsenal.")]


@pytest.mark.asyncio
async def test_stop_cancels_only_requested_user():
    initial = match()
    instance, _ = manager([initial])
    await instance.start("user-1", initial)
    await instance.start("user-2", initial)

    stopped = await instance.stop("user-1")

    assert stopped is True
    assert instance.is_active("user-1") is False
    assert instance.is_active("user-2") is True


@pytest.mark.asyncio
async def test_repeated_start_for_same_match_is_idempotent():
    initial = match()
    instance, _ = manager([initial])

    first = await instance.start("user-1", initial)
    second = await instance.start("user-1", initial)

    assert first is True
    assert second is False
