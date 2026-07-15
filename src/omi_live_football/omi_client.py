"""Client for sending direct Omi notifications."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from .config import Settings


class OmiNotificationClient:
    """Send match updates through the Omi direct notification API."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self.sleep = sleep

    async def send(self, uid: str, message: str) -> None:
        """Send one notification, retrying a rate-limited request once."""

        if not self.settings.omi_app_id or not self.settings.omi_app_secret:
            raise RuntimeError("OMI_APP_ID and OMI_APP_SECRET are required.")

        url = (
            f"{self.settings.omi_api_base_url.rstrip('/')}"
            f"/v2/integrations/{self.settings.omi_app_id}/notification"
        )
        for attempt in range(2):
            response = await self.client.post(
                url,
                params={"uid": uid, "message": message},
                headers={"Authorization": f"Bearer {self.settings.omi_app_secret}"},
            )
            if response.status_code == 429 and attempt == 0:
                await self.sleep(self._retry_after(response))
                continue
            response.raise_for_status()
            return

    async def aclose(self) -> None:
        """Close the internally owned HTTP client."""

        if self._owns_client:
            await self.client.aclose()

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        try:
            return max(0.0, float(response.headers.get("Retry-After", "1")))
        except ValueError:
            return 1.0

