from __future__ import annotations

from asyncio import gather
from collections.abc import Iterable

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context
from httpx import AsyncClient, codes

from mcp_app import config
from mcp_app.auth import AUTH_KEY, DOORAY_TAG

_PROXY_ERRORS = {
    codes.CONFLICT: "Dooray 개인 토큰이 등록되어 있지 않습니다. 어드민에서 먼저 등록하세요.",
    codes.UNAUTHORIZED: "Dooray 토큰이 유효하지 않거나 폐기되었습니다. 어드민에서 재등록하세요.",
    codes.FORBIDDEN: "허용되지 않은 Dooray 경로이거나 권한이 없습니다.",
}
_client = AsyncClient(base_url=config.API_BASE_URL, timeout=config.HTTP_TIMEOUT)


def _csv(value: str | Iterable[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return ",".join(str(v) for v in value)


async def _proxy(method: str, dooray_path: str, *, params: dict | None = None, data: dict | None = None) -> dict:
    resp = await _client.request(
        method,
        f"/v1/admin-api/proxy/dooray/{dooray_path.lstrip('/')}",
        params={k: v for k, v in (params or {}).items() if v is not None},
        json={k: v for k, v in (data or {}).items() if v is not None} or None,
        headers={"Authorization": f"Bearer {(await get_context().get_state(AUTH_KEY)).jwt}"},
    )
    if message := _PROXY_ERRORS.get(resp.status_code):
        raise ToolError(message)

    result = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
    header = result.get("header", {}) if isinstance(result, dict) else {}
    if resp.status_code >= codes.BAD_REQUEST or not header.get("isSuccessful", True):
        raise ToolError(f"Dooray API 오류: {header.get('resultMessage') or f'HTTP {resp.status_code}'}")
    return {k: v for k, v in result.items() if k != "header"} if isinstance(result, dict) else {"result": result}


def _members(ids: Iterable[str] | None) -> list[dict] | None:
    return [{"type": "member", "member": {"organizationMemberId": m}} for m in ids] if ids else None


def register(mcp: FastMCP) -> None:
    tag = {DOORAY_TAG}

    @mcp.tool(
        title="Dooray 프로젝트 목록",
        description="접근 가능한 Dooray 프로젝트 목록(project_id 발견용). member_me=True 면 내가 속한 프로젝트만.",
        tags=tag,
    )
    async def dooray_projects(member_me: bool = True, page: int = 0, size: int = 20) -> dict:
        return await _proxy(
            method="GET",
            dooray_path="/project/v1/projects",
            params={
                "member": "me" if member_me else None,
                "page": page,
                "size": size,
            },
        )

    @mcp.tool(
        title="Dooray 프로젝트 선택지",
        description=(
            "프로젝트의 workflow(업무상태)·member·milestone·tag 를 한 번에 조회. "
            "쓰기 전 유효 id(workflowId/organizationMemberId/milestoneId/tagId) 확보용. "
            "본인 organizationMemberId 는 `auth_status` 의 dooray.member_id 로 확인."
        ),
        tags=tag,
    )
    async def dooray_project_choices(project_id: str) -> dict:
        workflows, members, milestones, tags = await gather(
            _proxy(method="GET", dooray_path=f"/project/v1/projects/{project_id}/workflows"),
            _proxy(method="GET", dooray_path=f"/project/v1/projects/{project_id}/members", params={"size": 100}),
            _proxy(method="GET", dooray_path=f"/project/v1/projects/{project_id}/milestones", params={"size": 100}),
            _proxy(method="GET", dooray_path=f"/project/v1/projects/{project_id}/tags", params={"size": 100}),
        )
        return {
            "workflows": workflows.get("result"),
            "members": members.get("result"),
            "milestones": milestones.get("result"),
            "tags": tags.get("result"),
        }

    @mcp.tool(
        title="Dooray 업무 목록/검색",
        description=(
            "프로젝트 업무(Post) 목록. 필터는 콤마구분 문자열 또는 리스트. "
            "post_workflow_classes=backlog|registered|working|closed, "
            "date 필터(due_at/created_at/updated_at)=today|thisweek|prev-Nd|next-Nd|ISO8601범위, "
            "order=±postDueAt|postUpdatedAt|createdAt."
        ),
        tags=tag,
    )
    async def dooray_posts(
        project_id: str,
        page: int = 0,
        size: int = 20,
        post_workflow_classes: str | list[str] | None = None,
        post_workflow_ids: str | list[str] | None = None,
        tag_ids: str | list[str] | None = None,
        milestone_ids: str | list[str] | None = None,
        to_member_ids: str | list[str] | None = None,
        from_member_ids: str | list[str] | None = None,
        subjects: str | None = None,
        due_at: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        order: str | None = None,
    ) -> dict:
        return await _proxy(
            method="GET",
            dooray_path=f"/project/v1/projects/{project_id}/posts",
            params={
                "page": page,
                "size": size,
                "postWorkflowClasses": _csv(post_workflow_classes),
                "postWorkflowIds": _csv(post_workflow_ids),
                "tagIds": _csv(tag_ids),
                "milestoneIds": _csv(milestone_ids),
                "toMemberIds": _csv(to_member_ids),
                "fromMemberIds": _csv(from_member_ids),
                "subjects": subjects,
                "dueAt": due_at,
                "createdAt": created_at,
                "updatedAt": updated_at,
                "order": order,
            },
        )

    @mcp.tool(title="Dooray 업무 상세", description="특정 업무(Post) 상세 조회.", tags=tag)
    async def dooray_post(project_id: str, post_id: str) -> dict:
        return await _proxy(
            method="GET",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}",
        )

    @mcp.tool(title="Dooray 업무 댓글 목록", description="특정 업무의 댓글(log) 목록 조회.", tags=tag)
    async def dooray_post_comments(project_id: str, post_id: str) -> dict:
        return await _proxy(
            method="GET",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/logs",
        )

    @mcp.tool(
        title="Dooray 업무 생성",
        description=(
            "⚠️ Dooray 에 즉시 반영. 새 업무(Post)를 생성한다. 본문은 마크다운. "
            "담당자/참조자 id 는 `dooray_project_choices`(프로젝트 멤버)·`auth_status`의 dooray.member_id(본인)에서 확보. "
            "priority=highest|high|normal|low|lowest|none."
        ),
        tags=tag,
    )
    async def dooray_create_post(
        project_id: str,
        subject: str,
        body_markdown: str,
        to_member_ids: list[str] | None = None,
        cc_member_ids: list[str] | None = None,
        due_date: str | None = None,
        milestone_id: str | None = None,
        tag_ids: list[str] | None = None,
        priority: str | None = None,
        parent_post_id: str | None = None,
    ) -> dict:
        users = {}
        if to_member_ids:
            users["to"] = _members(to_member_ids)
        if cc_member_ids:
            users["cc"] = _members(cc_member_ids)

        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts",
            data={
                "subject": subject,
                "body": {"mimeType": "text/x-markdown", "content": body_markdown},
                "users": users or None,
                "dueDate": due_date,
                "milestoneId": milestone_id,
                "tagIds": tag_ids,
                "priority": priority,
                "parentPostId": parent_post_id,
            },
        )

    @mcp.tool(
        title="Dooray 업무 수정",
        description="⚠️ Dooray 에 즉시 반영. 업무의 제목/본문/담당자/만기/마일스톤/태그/우선순위를 수정(제공한 필드만).",
        tags=tag,
    )
    async def dooray_update_post(
        project_id: str,
        post_id: str,
        subject: str | None = None,
        body_markdown: str | None = None,
        to_member_ids: list[str] | None = None,
        cc_member_ids: list[str] | None = None,
        due_date: str | None = None,
        milestone_id: str | None = None,
        tag_ids: list[str] | None = None,
        priority: str | None = None,
    ) -> dict:
        users = {}
        if to_member_ids:
            users["to"] = _members(to_member_ids)
        if cc_member_ids:
            users["cc"] = _members(cc_member_ids)

        return await _proxy(
            method="PUT",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}",
            data={
                "subject": subject,
                "body": (
                    {"mimeType": "text/x-markdown", "content": body_markdown} if body_markdown is not None else None
                ),
                "users": users or None,
                "dueDate": due_date,
                "milestoneId": milestone_id,
                "tagIds": tag_ids,
                "priority": priority,
            },
        )

    @mcp.tool(
        title="Dooray 업무 상태 변경",
        description="⚠️ Dooray 에 즉시 반영. 업무 전체 상태를 workflow_id 로 변경(id 는 `dooray_project_choices`).",
        tags=tag,
    )
    async def dooray_set_post_workflow(project_id: str, post_id: str, workflow_id: str) -> dict:
        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/set-workflow",
            data={"workflowId": workflow_id},
        )

    @mcp.tool(
        title="Dooray 업무 완료 처리",
        description="⚠️ Dooray 에 즉시 반영. 업무를 완료(closed) 상태로 변경.",
        tags=tag,
    )
    async def dooray_set_post_done(project_id: str, post_id: str) -> dict:
        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/set-done",
        )

    @mcp.tool(
        title="Dooray 업무 댓글 작성",
        description="⚠️ Dooray 에 즉시 반영(담당자에게 알림). 업무에 댓글(마크다운)을 작성.",
        tags=tag,
    )
    async def dooray_add_post_comment(project_id: str, post_id: str, content_markdown: str) -> dict:
        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/logs",
            data={
                "body": {
                    "mimeType": "text/x-markdown",
                    "content": content_markdown,
                },
            },
        )
