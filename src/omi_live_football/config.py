"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the football tool."""

    popular_competitions: tuple[str, ...] = (
        "UEFA Champions League",
        "UEFA Europa League",
        "Premier League",
        "LaLiga",
        "Serie A",
        "Bundesliga",
        "Ligue 1",
        "FIFA World Cup",
        "UEFA European Championship",
        "Copa America",
    )
    popular_teams: tuple[str, ...] = ()
    omi_app_id: str = ""
    omi_app_secret: str = ""
    omi_api_base_url: str = "https://api.omi.me"
    live_poll_seconds: float = 20.0
    idle_poll_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from environment variables."""

        defaults = cls()
        return cls(
            popular_competitions=_csv("POPULAR_COMPETITIONS", defaults.popular_competitions),
            popular_teams=_csv("POPULAR_TEAMS", defaults.popular_teams),
            omi_app_id=os.getenv("OMI_APP_ID", ""),
            omi_app_secret=os.getenv("OMI_APP_SECRET", ""),
            omi_api_base_url=os.getenv("OMI_API_BASE_URL", defaults.omi_api_base_url),
            live_poll_seconds=float(os.getenv("LIVE_POLL_SECONDS", defaults.live_poll_seconds)),
            idle_poll_seconds=float(os.getenv("IDLE_POLL_SECONDS", defaults.idle_poll_seconds)),
        )
