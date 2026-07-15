"""FastAPI surface for the Omi football tool."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import FastAPI

from .config import Settings
from .easy_soccer import EasySoccerService
from .football_tool import FootballTool, ToolRequest
from .live_commentary import LiveCommentaryManager
from .omi_client import OmiNotificationClient


class ToolHandler(Protocol):
    async def handle(self, request: ToolRequest) -> dict[str, str]: ...


def build_manifest() -> dict[str, Any]:
    """Return the Omi Chat Tools manifest."""

    return {
        "tools": [
            {
                "name": "football_match",
                "description": (
                    "Look up football scores, match progress, formations, players, "
                    "coaches, incidents, and statistics. Also start or stop live text "
                    "commentary when the user explicitly requests continuous match updates."
                ),
                "endpoint": "/tools/football-match",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "query",
                                "start_commentary",
                                "stop_commentary",
                            ],
                            "description": "The football operation requested by the user.",
                        },
                        "match_query": {
                            "type": "string",
                            "description": ("Team names and optionally a date or competition."),
                        },
                        "match_id": {
                            "type": "integer",
                            "description": "A previously resolved provider match ID.",
                        },
                        "date": {
                            "type": "string",
                            "description": "Optional match date in YYYY-MM-DD format.",
                        },
                        "competition": {
                            "type": "string",
                            "description": "Optional competition name.",
                        },
                    },
                    "required": ["action"],
                },
                "auth_required": True,
                "status_message": "Checking the football match...",
            }
        ]
    }


def create_app(
    tool: ToolHandler,
    *,
    lifespan: Callable[[FastAPI], Any] | None = None,
) -> FastAPI:
    """Create the HTTP application with an injected tool handler."""

    app = FastAPI(title="Omi Live Football", lifespan=lifespan)

    @app.get("/.well-known/omi-tools.json")
    async def manifest() -> dict[str, Any]:
        return build_manifest()

    @app.post("/tools/football-match")
    async def football_match(request: ToolRequest) -> dict[str, str]:
        return await tool.handle(request)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_default_app(settings: Settings | None = None) -> FastAPI:
    """Compose the production application using one in-memory process."""

    runtime_settings = settings or Settings.from_env()
    soccer = EasySoccerService(settings=runtime_settings)
    notifier = OmiNotificationClient(runtime_settings)
    commentary = LiveCommentaryManager(
        soccer=soccer,
        notifier=notifier,
        settings=runtime_settings,
    )
    tool = FootballTool(soccer=soccer, commentary=commentary)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await commentary.close()
            await notifier.aclose()

    application = create_app(tool, lifespan=lifespan)
    application.state.commentary = commentary
    application.state.notification_client = notifier
    return application


app = create_default_app()
