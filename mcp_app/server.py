import httpx
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context
from fastmcp.server.providers.openapi import (
    OpenAPIResource,
    OpenAPIResourceTemplate,
    OpenAPITool,
)
from fastmcp.tools.base import ToolResult
from fastmcp.utilities.openapi import HTTPRoute
from fastmcp.utilities.types import Image
from mcp.types import TextContent

from mcp_app import config
from mcp_app import mdx_components as mdx
from mcp_app import mdx_preview as preview
from mcp_app.auth import ADMIN_TAG, AUTH_KEY, AuthMiddleware, AuthState, CurrentAuth
from mcp_app.routes import ROUTE_MAPS, lookup

LANG_KEY = "language"
_SUPPORTED_LANGS = ("ko", "en")
_GUIDANCE_ADMIN = (
    "공개+어드민 도구(CMS 페이지·사이트맵 쓰기, 대시보드, 주문·상품·카테고리 읽기)를 쓸 수 있습니다. "
    "쓰기 전 입력 스키마의 x-ui-schema(위젯), x-translation(*_ko/*_en), x-relation(FK/M2M 대상)을 확인하고, "
    "관계 필드는 choices 도구로 유효 id 를 채우세요. "
    "CMS 섹션 body 는 MDX — 컴포넌트·props 는 `mdx_components`, 미리보기는 `mdx_preview` "
    "(둘 다 domain 인자: `도메인 그룹 목록`의 실제 호스트, 예 2026.pycon.kr)."
)
_GUIDANCE_PUBLIC = (
    "공개 도구(후원사·발표·이벤트 조회)를 사용할 수 있습니다. 더 많은 기능이 필요하면 유효한 토큰으로 다시 연결하세요."
)


def _customize_component(route: HTTPRoute, component: OpenAPITool | OpenAPIResource | OpenAPIResourceTemplate) -> None:
    if (doc := lookup(route.method.upper(), route.path)) is None:
        return
    component.title = doc.summary
    component.description = doc.description


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
            "PyCon Korea(파이콘 한국) MCP 서버. 먼저 `auth_status` 로 가능한 기능을 확인하세요. "
            "응답 언어는 `set_language`(ko=기본/en)."
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
            "CMS 본문(MDX)에 쓸 수 있는 컴포넌트·props 조회. domain 은 `도메인 그룹 목록`의 실제 호스트(예: 2026.pycon.kr). "
            "component 를 비우면 목록, 채우면 props 상세. group(mui|common|shop)으로 필터."
        ),
        tags={ADMIN_TAG},
    )
    async def mdx_components(domain: str, component: str | None = None, group: str | None = None) -> dict:
        if component:
            return await mdx.detail(domain, component)
        return await mdx.compact(domain, group)

    @mcp.tool(
        title="MDX 렌더링 미리보기",
        description=(
            "작성한 MDX 를 실제 프론트(domain)에서 렌더해 HTML+스크린샷 반환(페이지·섹션 생성 없이). "
            "domain 은 `도메인 그룹 목록`의 실제 호스트(예: 2026.pycon.kr), mdx 는 섹션 본문. "
            "html_scope=content(기본)|document. 그 외 파라미터로 CSS·제목·배너·뷰포트·캡처 범위를 조정."
        ),
        tags={ADMIN_TAG},
    )
    async def mdx_preview(
        domain: str,
        mdx: str,
        section_css: str | None = None,
        page_css: str | None = None,
        title: str | None = None,
        show_top_title_banner: bool = False,
        show_bottom_sponsor_banner: bool = False,
        viewport_width: int = 1280,
        full_page: bool = True,
        html_scope: str = "content",
        include_screenshot: bool = True,
    ) -> ToolResult:
        if html_scope not in ("content", "document"):
            raise ToolError("html_scope 는 content 또는 document 여야 합니다.")
        result = await preview.render(
            domain,
            [{"id": "preview", "css": section_css, "body": mdx}],
            title=title,
            page_css=page_css,
            show_top_title_banner=show_top_title_banner,
            show_bottom_sponsor_banner=show_bottom_sponsor_banner,
            viewport_width=viewport_width,
            full_page=full_page,
            html_scope=html_scope,
            include_screenshot=include_screenshot,
        )
        blocks: list = []
        if result.get("screenshot_png"):
            blocks.append(Image(data=result["screenshot_png"], format="png").to_image_content())
        blocks.append(TextContent(type="text", text=result["html"]))
        return ToolResult(
            content=blocks,
            structured_content={"url": result["url"], "scope": html_scope},
        )

    return mcp
