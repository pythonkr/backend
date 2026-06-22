from __future__ import annotations

from collections import Counter
from time import monotonic

from fastmcp.exceptions import ToolError
from httpx import AsyncClient, HTTPError

from mcp_app import config

_CACHE_TTL = 300.0
_cache: dict[str, tuple[float, dict]] = {}


async def _fetch(domain: str) -> dict:
    if not (host := domain.strip().lower()):
        raise ToolError(
            "domain 에 프론트엔드 호스트가 필요합니다 (예: 2026.pycon.kr). 도메인 그룹 목록 도구로 유효한 도메인을 확인하세요."
        )

    url = f"https://{host}/.well-known/mdx-components.json"
    now = monotonic()
    if (hit := _cache.get(url)) and hit[0] > now:
        return hit[1]
    try:
        async with AsyncClient(timeout=config.HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
    except HTTPError as exc:
        raise ToolError(f"{domain}에 대한 매니페스트를 가져오지 못했습니다: {exc}") from exc
    if resp.status_code == 404:
        raise ToolError(
            f"{domain}에 매니페스트가 없습니다(404). 해당 프론트엔드가 아직 mdx-components.json 을 배포하지 않았거나 도메인이 잘못됐을 수 있습니다."
        )
    if resp.status_code != 200:
        raise ToolError(f"{domain}에서 매니페스트를 가져오지 못했습니다. 응답 오류: HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ToolError(f"{domain} 도메인의 매니페스트 응답이 JSON 이 아닙니다: {exc}") from exc
    _cache[url] = (now + _CACHE_TTL, data)
    return data


async def compact(domain: str, group: str | None = None) -> dict:
    data = dict(await _fetch(domain))  # 캐시 원본 보존을 위한 얕은 복사 — 아래 pop 이 캐시를 변형하지 않도록
    components = data.pop("components", [])
    if group:
        components = [c for c in components if c["group"] == group.lower()]
    return {
        **data,
        "counts": dict(Counter(c["group"] for c in components)),
        "components": [
            {
                "name": c["name"],
                "group": c["group"],
                "description": c.get("description"),
                "propCount": len(c["props"]) if isinstance(c.get("props"), list) else None,
            }
            for c in components
        ],
        "hint": (
            "특정 컴포넌트의 props 는 component=<이름> 으로 상세 조회하세요. "
            "Mui__* 컴포넌트는 props 설명이 없으니 muiVersion 기준 MUI 공식 문서(muiDocsBaseUrl)를 참고하세요. "
            "MDX 본문에서는 이름 그대로 JSX 태그로 사용합니다(예: <Common__Components__MDX__FAQAccordion .../>)."
        ),
    }


async def detail(domain: str, name: str) -> dict:
    components = (await _fetch(domain)).get("components", [])
    for c in components:
        if c.get("name") == name:
            return c
    suggestions = [n for c in components if (n := c.get("name")) and name.lower() in n.lower()][:10]
    raise ToolError(
        f"컴포넌트 '{name}' 을(를) {domain} 매니페스트에서 찾지 못했습니다."
        + (f" 비슷한 이름: {suggestions}" if suggestions else " (목록은 component 없이 호출해 확인하세요.)")
    )
