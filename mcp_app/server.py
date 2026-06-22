from __future__ import annotations

import httpx
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context
from fastmcp.server.providers.openapi import (
    OpenAPIResource,
    OpenAPIResourceTemplate,
    OpenAPITool,
)
from fastmcp.utilities.openapi import HTTPRoute

from mcp_app import config
from mcp_app import mdx_components as mdx
from mcp_app.auth import ADMIN_TAG, AUTH_KEY, AuthMiddleware, AuthState, CurrentAuth
from mcp_app.routes import ROUTE_MAPS, lookup

LANG_KEY = "language"
_SUPPORTED_LANGS = ("ko", "en")
_GUIDANCE_ADMIN = (
    "공개 도구 + 어드민 도구(CMS 페이지·사이트맵 쓰기, 대시보드 통계, 주문·상품·카테고리 조회)를 사용할 수 있습니다. "
    "쓰기 시 생성/수정 도구의 입력 스키마를 참고하세요 — 각 필드에 x-ui-schema(위젯; markdown 여부), "
    "x-translation({of,language}; *_ko/*_en 매핑), x-relation({model,many}; FK/M2M 대상)이 붙습니다. "
    "관계 필드 값은 해당 리소스의 choices 도구로 유효 id 를 확인해 채우세요. "
    "CMS 본문(섹션 body)은 Markdown 이 아니라 MDX 입니다 — 사용 가능한 컴포넌트와 props 는 `mdx_components` 도구로 확인하세요. "
    "컴포넌트 목록은 프론트엔드 도메인(앱)마다 다르므로, 먼저 `도메인 그룹 목록`으로 해당 페이지의 "
    "domain_group → 실제 도메인(예: 2026.pycon.kr)을 확인한 뒤 그 도메인으로 호출하세요."
)
_GUIDANCE_PUBLIC = (
    "공개 도구(후원사·발표·이벤트 조회)를 사용할 수 있습니다. 더 많은 기능이 필요하면 유효한 토큰으로 다시 연결하세요."
)


def _customize_component(route: HTTPRoute, component: OpenAPITool | OpenAPIResource | OpenAPIResourceTemplate) -> None:
    method, path = route.method.upper(), route.path
    if (doc := lookup(method, path)) is None:
        return
    component.title = doc.summary
    component.description = "\n\n".join(filter(None, [doc.description, f"호출: {method} {path}"]))


async def _forward_headers(request: httpx.Request) -> None:
    ctx = get_context()
    auth: AuthState = await ctx.get_state(AUTH_KEY)
    if auth.is_admin:
        request.headers["Authorization"] = f"Bearer {auth.jwt}"
    if lang := await ctx.get_state(LANG_KEY):
        request.headers["Accept-Language"] = lang


def build() -> FastMCP:
    mcp = FastMCP.from_openapi(
        name="pyconkr",
        instructions=(
            "PyCon Korea(파이콘 한국 — 한국에서 열리는 Python 언어 컨퍼런스)의 MCP 서버입니다. "
            "먼저 `auth_status` 로 사용 가능한 기능을 확인하세요. "
            "응답 언어는 `set_language` 로 바꿀 수 있습니다(`ko`=한국어 기본, `en`=영어)."
        ),
        route_maps=ROUTE_MAPS,
        mcp_component_fn=_customize_component,
        validate_output=False,
        openapi_spec=httpx.get(
            f"{config.API_BASE_URL}/api/schema/v1/",
            headers={"Accept": "application/json"},
            timeout=config.HTTP_TIMEOUT,
        )
        .raise_for_status()
        .json(),
        client=httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            timeout=config.HTTP_TIMEOUT,
            event_hooks={"request": [_forward_headers]},
        ),
    )
    mcp.add_middleware(AuthMiddleware())

    @mcp.tool(title="인증 상태 확인", description="현재 인증 상태와 사용 가능한 기능·사용법을 확인한다.")
    async def auth_status(auth: AuthState = CurrentAuth()) -> dict:  # noqa: B008
        return {
            "status": auth.status.value,
            "username": auth.username,
            "message": auth.status_message,
            "guidance": _GUIDANCE_ADMIN if auth.is_admin else _GUIDANCE_PUBLIC,
        }

    @mcp.tool(
        title="응답 언어 설정",
        description="이후 호출의 응답 언어를 설정한다(`ko`=한국어, `en`=영어; 기본 `ko`). 세션 동안 유지된다.",
    )
    async def set_language(language: str, ctx: Context) -> dict:
        if (lang := language.lower()) not in _SUPPORTED_LANGS:
            raise ToolError(f"language 는 {' 또는 '.join(_SUPPORTED_LANGS)} 여야 합니다.")
        await ctx.set_state(LANG_KEY, lang)
        return {"language": lang}

    @mcp.tool(
        title="MDX 컴포넌트 조회",
        description=(
            "CMS 본문(MDX)에서 쓸 수 있는 컴포넌트와 props 를 조회한다. 컴포넌트 집합은 프론트엔드 도메인(앱)마다 다르므로 "
            "`도메인 그룹 목록`으로 확인한 실제 호스트를 domain 에 넣는다(예: 2026.pycon.kr). "
            "component 를 비우면 목록(이름·group·요약), 채우면 그 컴포넌트의 props 상세를 반환한다. "
            "group(mui|common|shop)으로 목록을 좁힐 수 있다. "
            "Mui__* 컴포넌트는 props 설명이 없으니 응답의 muiVersion 기준 MUI 공식 문서를 참고한다."
        ),
        tags={ADMIN_TAG},
    )
    async def mdx_components(domain: str, component: str | None = None, group: str | None = None) -> dict:
        if component:
            return await mdx.detail(domain, component)
        return await mdx.compact(domain, group)

    return mcp
