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
from mcp_app.auth import AUTH_KEY, AuthMiddleware, AuthState, CurrentAuth
from mcp_app.routes import ROUTE_MAPS, lookup

LANG_KEY = "language"
_SUPPORTED_LANGS = ("ko", "en")
_GUIDANCE_ADMIN = (
    "공개 도구 + 어드민 도구(CMS 페이지·사이트맵 쓰기, 대시보드 통계, 주문·상품·카테고리 조회)를 사용할 수 있습니다. "
    "쓰기 시 생성/수정 도구의 입력 스키마를 참고하세요 — 각 필드에 x-ui-schema(위젯; markdown 여부), "
    "x-translation({of,language}; *_ko/*_en 매핑), x-relation({model,many}; FK/M2M 대상)이 붙습니다. "
    "관계 필드 값은 해당 리소스의 choices 도구로 유효 id 를 확인해 채우세요."
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

    return mcp
