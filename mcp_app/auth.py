from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import httpx
from fastmcp import Context
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_app import config

ADMIN_TAG = "admin"  # 이 태그가 붙은 도구는 인증된 어드민(슈퍼유저)에게만 노출
AUTH_KEY = "auth_state"


class AuthStatus(StrEnum):
    ANONYMOUS = "anonymous"
    AUTH_FAILED = "auth_failed"
    AUTHENTICATED = "authenticated"


@dataclass
class AuthState:
    status: AuthStatus
    username: str | None = None
    jwt: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.status is AuthStatus.AUTHENTICATED

    @property
    def status_message(self) -> str:
        if self.status is AuthStatus.AUTH_FAILED:
            return "토큰 인증에 실패했습니다(만료/폐기 등). 어드민에서 재발급하세요. 지금은 공개 도구만 사용할 수 있습니다."
        if self.is_admin:
            return "어드민으로 인증되었습니다. 어드민 도구를 사용할 수 있습니다."
        return "공개 도구만 사용할 수 있습니다."

    @classmethod
    async def from_authorization(cls, authorization: str | None) -> AuthState:
        jwt = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
        if not jwt:
            return cls(AuthStatus.ANONYMOUS)
        async with httpx.AsyncClient(base_url=config.API_BASE_URL, timeout=config.HTTP_TIMEOUT) as client:
            resp = await client.get("/v1/admin-api/user/userext/me/", headers={"Authorization": f"Bearer {jwt}"})
        if resp.status_code != 200:
            return cls(AuthStatus.AUTH_FAILED, jwt=jwt)
        data = resp.json()
        if not data.get("is_superuser"):
            return cls(AuthStatus.ANONYMOUS, jwt=jwt)
        return cls(AuthStatus.AUTHENTICATED, username=data.get("username"), jwt=jwt)


def CurrentAuth() -> AuthState:
    async def current_auth(ctx: Context = CurrentContext()) -> AuthState:  # noqa: B008
        return await ctx.get_state(AUTH_KEY)

    return cast(AuthState, Depends(current_auth))


def _is_admin_tool(tool) -> bool:
    return ADMIN_TAG in (tool.tags or set())


class AuthMiddleware(Middleware):
    async def on_request(self, context: MiddlewareContext, call_next):
        await context.fastmcp_context.set_state(
            AUTH_KEY,
            await AuthState.from_authorization(get_http_headers(include={"authorization"}).get("authorization")),
            serializable=False,
        )
        return await call_next(context)

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        tools = await call_next(context)
        if (await context.fastmcp_context.get_state(AUTH_KEY)).is_admin:
            return tools
        return [t for t in tools if not _is_admin_tool(t)]

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
        auth: AuthState = await context.fastmcp_context.get_state(AUTH_KEY)
        if tool and _is_admin_tool(tool) and not auth.is_admin:
            raise ToolError("이 도구는 인증된 어드민(슈퍼유저)만 사용할 수 있습니다. auth_status 로 상태를 확인하세요.")
        return await call_next(context)
