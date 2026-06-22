from contextlib import suppress

from fastmcp.exceptions import ToolError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from mcp_app import config
from mcp_app.util import require_host

_MESSAGE_TYPE = "pyconkr:mdx-preview"
_READY_SELECTOR = "html[data-mdx-preview='ready']"
_CONTENT_SELECTOR = "[data-mdx-preview-content]"
_SETTLE_MS = 600
_TIMEOUT_MS = int(config.BROWSER_TIMEOUT * 1000)


async def render(
    domain: str,
    sections: list[dict],
    *,
    title: str | None = None,
    page_css: str | None = None,
    show_top_title_banner: bool = False,
    show_bottom_sponsor_banner: bool = False,
    viewport_width: int = 1280,
    full_page: bool = True,
    html_scope: str = "content",
    include_screenshot: bool = True,
) -> dict:
    url = f"https://{require_host(domain)}/preview"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await (
                await browser.new_context(
                    viewport={"width": max(320, viewport_width), "height": 900},
                    ignore_https_errors=True,  # 로컬 dev(mkcert) 인증서 허용
                )
            ).new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
                await page.wait_for_selector(_READY_SELECTOR, timeout=_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                msg = f"{domain} 의 미리보기 라우트 접근 실패. 해당 프론트엔드에 /preview 라우트가 있는지, domain 이 올바른지 확인하세요."
                raise ToolError(msg) from exc
            await page.evaluate(
                f"(payload) => window.postMessage({{ type: {_MESSAGE_TYPE!r}, payload }}, window.location.origin)",
                {
                    "css": page_css,
                    "title": title,
                    "show_top_title_banner": show_top_title_banner,
                    "show_bottom_sponsor_banner": show_bottom_sponsor_banner,
                    "sections": sections,
                },
            )
            await page.wait_for_selector(_CONTENT_SELECTOR, timeout=_TIMEOUT_MS)
            with suppress(PlaywrightTimeoutError):
                await page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)
            await page.wait_for_timeout(_SETTLE_MS)

            if html_scope == "document":
                html = await page.content()
            else:
                node = await page.query_selector(_CONTENT_SELECTOR)
                html = await node.evaluate("el => el.outerHTML") if node else ""

            screenshot = await page.screenshot(full_page=full_page, type="png") if include_screenshot else None
        except PlaywrightError as exc:
            raise ToolError(f"미리보기 렌더링에 실패했습니다: {exc}") from exc
        finally:
            await browser.close()

    return {"url": url, "html": html, "screenshot_png": screenshot}
