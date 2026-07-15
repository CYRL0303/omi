import httpx
import pytest
import respx

from omi_live_football.config import Settings
from omi_live_football.omi_client import OmiNotificationClient


@pytest.mark.asyncio
@respx.mock
async def test_notification_uses_omi_direct_notification_contract():
    route = respx.post("https://api.omi.me/v2/integrations/app-1/notification").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = OmiNotificationClient(Settings(omi_app_id="app-1", omi_app_secret="secret-1"))

    await client.send("user-1", "Goal for Real Madrid.")

    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-1"
    assert request.url.params["uid"] == "user-1"
    assert request.url.params["message"] == "Goal for Real Madrid."
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_notification_obeys_retry_after_once():
    route = respx.post("https://api.omi.me/v2/integrations/app-1/notification").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    delays = []

    async def record_sleep(seconds):
        delays.append(seconds)

    client = OmiNotificationClient(
        Settings(omi_app_id="app-1", omi_app_secret="secret-1"),
        sleep=record_sleep,
    )

    await client.send("user-1", "Match update.")

    assert len(route.calls) == 2
    assert delays == [3.0]
    await client.aclose()


@pytest.mark.asyncio
async def test_notification_requires_app_credentials():
    client = OmiNotificationClient(Settings())

    with pytest.raises(RuntimeError, match="OMI_APP_ID and OMI_APP_SECRET"):
        await client.send("user-1", "Match update.")

    await client.aclose()
