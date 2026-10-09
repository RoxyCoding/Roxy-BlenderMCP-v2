"""ambientCG: search over its v3 API (mocked here) and import through the addon."""

import asyncio

import httpx
import pytest

from blender_mcp import ambientcg, server

ASSETS = {
    "totalResults": 2,
    "assets": [
        {"id": "Tatami001", "tags": ["tatami", "floor"], "maps": ["color", "normal", "roughness"],
         "dimensions": {"width": 250, "height": 250, "depth": 0}},
        {"id": "Tatami002", "tags": ["tatami"], "maps": ["color"], "dimensions": {"width": 0, "height": 0}},
    ],
}


@pytest.fixture
def api(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=ASSETS)

    real = httpx.AsyncClient
    monkeypatch.setattr(ambientcg.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


def test_search_lists_ids_sizes_and_credit(api):
    listing = asyncio.run(ambientcg.search("tatami", limit=5))
    assert "(ID: Tatami001)" in listing and "Real-world size: 2.5m x 2.5m" in listing
    assert "Real-world size: not given" in listing
    assert "CC0" in listing
    params = api[0].url.params
    assert params["type"] == "material" and params["q"] == "tatami" and params["limit"] == "5"


def test_search_only_does_materials():
    assert asyncio.run(ambientcg.search("x", asset_type="hdris")).startswith("Error")


def test_search_assets_routes_to_ambientcg(api):
    out = asyncio.run(server.search_assets(None, source="ambientcg", query="tatami"))
    assert "Tatami001" in out


class FakeBlender:
    def __init__(self, reply):
        self.reply, self.sent = reply, []

    def send_command(self, command, params=None, read_only=False):
        self.sent.append((command, params))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _import(monkeypatch, reply, **kw):
    blender = FakeBlender(reply)
    monkeypatch.setattr(server, "get_blender_connection", lambda: blender)
    out = asyncio.run(server.import_asset(None, source="ambientcg", id="Tatami001", **kw))
    return out, blender


def test_import_reports_material_scale_and_where_it_went(monkeypatch):
    out, blender = _import(monkeypatch, {
        "success": True, "material": "Tatami001", "maps": ["Color", "NormalGL"], "resolution": "2K-JPG",
        "size_m": [2.5, 2.5], "applied": ["Floor"], "not_found": ["Nope"], "url": "https://ambientcg.com/view?id=Tatami001",
    }, apply_to=["Floor", "Nope"], resolution="2k")
    assert blender.sent == [("download_ambientcg_material", {
        "asset_id": "Tatami001", "resolution": "2K", "file_format": "JPG", "apply_to": ["Floor", "Nope"]})]
    assert "2.5 x 2.5 m" in out and "Applied to: Floor" in out and "Not found, so not applied: Nope" in out
    assert "CC0" in out


def test_import_relays_addon_errors(monkeypatch):
    out, _ = _import(monkeypatch, {"error": "Tatami001 has no 3K-JPG download. Available: 1K-JPG"})
    assert out.startswith("Error: Tatami001 has no 3K-JPG")


def test_old_addon_is_told_to_update(monkeypatch):
    monkeypatch.setattr(server, "_addon_outdated", lambda: True)
    out, _ = _import(monkeypatch, Exception("Unknown command type: download_ambientcg_material"))
    assert "ambientCG" in out and "too old" in out
