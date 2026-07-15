import re
from pathlib import Path

import httpx
import pytest

from omi_live_football.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_default_application_serves_health_and_manifest():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/healthz")
        manifest = await client.get("/.well-known/omi-tools.json")

    assert health.json() == {"status": "ok"}
    assert len(manifest.json()["tools"]) == 1
    assert manifest.json()["tools"][0]["name"] == "football_match"


def test_docker_runs_one_application_worker():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "omi_live_football.main:app" in dockerfile
    assert '"--workers", "1"' in dockerfile


def test_environment_example_lists_required_omi_credentials():
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "OMI_APP_ID=" in example
    assert "OMI_APP_SECRET=" in example
    assert "LIVE_POLL_SECONDS=20" in example


def test_application_controlled_files_contain_no_chinese_characters():
    roots = [
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "tests",
    ]
    files = [PROJECT_ROOT / "README.md", PROJECT_ROOT / ".env.example"]
    for root in roots:
        files.extend(root.rglob("*.py"))

    chinese = re.compile(r"[\u4e00-\u9fff]")
    violations = [
        str(path.relative_to(PROJECT_ROOT))
        for path in files
        if chinese.search(path.read_text(encoding="utf-8"))
    ]

    assert violations == []
