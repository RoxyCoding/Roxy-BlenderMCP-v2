"""ambientCG (https://ambientcg.com): searching its CC0 materials.

Searching is plain HTTP, so the server does it; downloading happens in the
Blender addon (download_ambientcg_material), where the files have to land.
"""

from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger("BlenderMCPServer")

API = "https://ambientcg.com/api/v3/assets"
SITE = "https://ambientcg.com"
HEADERS = {"User-Agent": "roxy-blender-mcp"}
CREDIT = "Materials from ambientCG (https://ambientcg.com), free and CC0."
# Only materials for now; the API also has HDRIs, decals and models.
TYPES = {"all": "material", "materials": "material", "textures": "material"}


def _size(asset: dict) -> str | None:
    dims = asset.get("dimensions") or {}
    width, height = dims.get("width") or 0, dims.get("height") or 0
    return f"{width / 100:g}m x {height / 100:g}m" if width > 0 and height > 0 else None


async def search(query: str, asset_type: str = "all", limit: int = 20) -> str:
    kind = TYPES.get((asset_type or "all").lower())
    if kind is None:
        return f"Error: ambientcg supports asset_type materials only (got {asset_type!r})."
    params = {"type": kind, "limit": limit, "include": "dimensions,maps,tags"}
    if query:
        params["q"] = query
    else:
        params["sort"] = "popular"
    async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
        response = await client.get(API, params=params)
        response.raise_for_status()
        data = response.json()

    assets = data.get("assets") or []
    total = data.get("totalResults", len(assets))
    header = f"{total} materials on ambientCG" + (f" match '{query}'" if query else ", most popular first")
    if not assets:
        return f"{header}. Try fewer or broader words (ambientCG matches every word)."
    lines = [header, f"Showing {len(assets)}:", ""]
    for asset in assets:
        lines.append(f"- {asset['id']} (ID: {asset['id']})  |  {SITE}/view?id={asset['id']}")
        if asset.get("tags"):
            lines.append(f"  Tags: {', '.join(asset['tags'])}")
        if asset.get("maps"):
            lines.append(f"  Maps: {', '.join(asset['maps'])}")
        size = _size(asset)
        lines.append(f"  Real-world size: {size}" if size else "  Real-world size: not given")
        lines.append("")
    lines.append(CREDIT)
    return "\n".join(lines)


def thumbnails(ids: list[str]) -> list[tuple[str, str]]:
    """(base64 JPEG, mime type) for each id's 256px thumbnail; failures are skipped."""
    if not ids:
        return []
    out = []
    try:
        with httpx.Client(headers=HEADERS, timeout=20) as client:
            response = client.get(API, params={"id": ",".join(ids), "include": "thumbnails"})
            response.raise_for_status()
            by_id = {a["id"]: a for a in response.json().get("assets") or []}
            for ident in ids:
                url = ((by_id.get(ident) or {}).get("thumbnails") or {}).get("256-JPG-FFFFFF")
                if not url:
                    continue
                image = client.get(url)
                if image.status_code == 200:
                    out.append((base64.b64encode(image.content).decode("ascii"), "image/jpeg"))
    except Exception as e:
        logger.debug(f"ambientCG thumbnails failed: {e}")
    return out
