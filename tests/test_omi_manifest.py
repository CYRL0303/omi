import httpx
import pytest

from omi_live_football.main import build_manifest, create_app


class FakeTool:
    async def handle(self, request):
        return {"result": f"Handled {request.action}."}


def test_manifest_exposes_exactly_one_football_tool():
    manifest = build_manifest()

    assert len(manifest["tools"]) == 1
    tool = manifest["tools"][0]
    assert tool["name"] == "football_match"
    assert tool["endpoint"] == "/tools/football-match"
    assert tool["method"] == "POST"
    assert tool["auth_required"] is True
    assert tool["parameters"]["properties"]["action"]["enum"] == [
        "query",
        "start_commentary",
        "stop_commentary",
    ]
    assert tool["parameters"]["required"] == ["action"]


@pytest.mark.asyncio
async def test_fastapi_endpoint_returns_omi_result_shape():
    transport = httpx.ASGITransport(app=create_app(FakeTool()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/tools/football-match",
            json={
                "uid": "user-1",
                "app_id": "app-1",
                "tool_name": "football_match",
                "action": "query",
                "match_query": "Real Madrid Arsenal",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"result": "Handled query."}


@pytest.mark.asyncio
async def test_manifest_is_available_at_omi_well_known_path():
    transport = httpx.ASGITransport(app=create_app(FakeTool()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/.well-known/omi-tools.json")

    assert response.status_code == 200
    assert response.json() == build_manifest()
