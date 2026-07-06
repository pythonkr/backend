from __future__ import annotations

from asyncio import Semaphore, gather
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


async def _proxy(
    method: str,
    dooray_path: str,
    *,
    params: dict | None = None,
    data: dict | None = None,
    keep_data_nulls: Iterable[str] = (),
) -> dict:
    keep = set(keep_data_nulls)
    body = {k: v for k, v in (data or {}).items() if v is not None or k in keep}
    resp = await _client.request(
        method,
        f"/v1/admin-api/proxy/dooray/{dooray_path.lstrip('/')}",
        params={k: v for k, v in (params or {}).items() if v is not None},
        json=body or None,
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


def _users(to_member_ids: Iterable[str] | None, cc_member_ids: Iterable[str] | None) -> dict | None:
    users = {}
    if to := _members(to_member_ids):
        users["to"] = to
    if cc := _members(cc_member_ids):
        users["cc"] = cc
    return users or None


async def _with_member_names(rows: list[dict]) -> list[dict]:
    sem = Semaphore(8)

    async def _one(member_id: str) -> tuple[str, dict]:
        async with sem:
            try:
                detail = await _proxy(method="GET", dooray_path=f"/common/v1/members/{member_id}")
            except ToolError:
                return member_id, {}
        return member_id, detail.get("result") or {}

    resolved = dict(await gather(*(_one(r["organizationMemberId"]) for r in rows)))
    return [
        {**r, "name": (d := resolved.get(r["organizationMemberId"]) or {}).get("name"), "userCode": d.get("userCode")}
        for r in rows
    ]


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
            "프로젝트의 workflow(업무상태)·member(이름 포함)·milestone·tag 를 한 번에 조회. "
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
            "members": await _with_member_names(members.get("result") or []),
            "milestones": milestones.get("result"),
            "tags": tags.get("result"),
        }

    @mcp.tool(
        title="Dooray 업무 목록/검색",
        description=(
            "프로젝트 업무(Post) 목록. 필터는 콤마구분 문자열 또는 리스트. "
            "post_workflow_classes=backlog|registered|working|closed, "
            "to_member_ids/from_member_ids=담당자/작성자(organizationMemberId), subjects=제목 필터, "
            "date 필터(due_at/created_at/updated_at)=today|thisweek|prev-Nd|next-Nd|ISO8601범위, "
            "order=±postDueAt|postUpdatedAt|createdAt. 본문 body 는 미포함(상세는 `dooray_post`)."
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

    @mcp.tool(title="Dooray 업무 상세", description="특정 업무(Post) 상세 조회(목록과 달리 본문 body 포함).", tags=tag)
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
            "priority=highest|high|normal|low|lowest|none. "
            "workflow_id 지정 시 생성 직후 해당 상태로 이동(미지정이면 프로젝트 기본 상태=보통 보류/등록)."
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
        workflow_id: str | None = None,
    ) -> dict:
        created = await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts",
            data={
                "subject": subject,
                "body": {"mimeType": "text/x-markdown", "content": body_markdown},
                "users": _users(to_member_ids, cc_member_ids),
                "dueDate": due_date,
                "milestoneId": milestone_id,
                "tagIds": tag_ids,
                "priority": priority,
                "parentPostId": parent_post_id,
            },
        )
        if workflow_id and (post_id := (created.get("result") or {}).get("id")):
            await _proxy(
                method="POST",
                dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/set-workflow",
                data={"workflowId": workflow_id},
            )
        return created

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
        return await _proxy(
            method="PUT",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}",
            data={
                "subject": subject,
                "body": (
                    {"mimeType": "text/x-markdown", "content": body_markdown} if body_markdown is not None else None
                ),
                "users": _users(to_member_ids, cc_member_ids),
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
        description=(
            "⚠️ Dooray 에 즉시 반영. 업무를 완료(closed) 상태로 변경. "
            "‼️ 업무 삭제(휴지통)는 이 도구(및 Dooray API)로 불가 — 완료 처리가 최대치다. "
            "정말 지우려면 Dooray 웹 UI에서 수동으로만 가능."
        ),
        tags=tag,
    )
    async def dooray_set_post_done(project_id: str, post_id: str) -> dict:
        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/set-done",
        )

    @mcp.tool(
        title="Dooray 업무 상위(에픽) 설정/해제",
        description=(
            "⚠️ Dooray 에 즉시 반영. 기존 업무의 상위 업무(에픽 등)를 설정하거나 해제한다. "
            "parent_post_id 지정=그 업무의 하위로 묶기, 미지정(None)=상위 해제(최상위로). "
            "제약: 이미 하위 업무를 가진 업무는 다른 업무의 하위로 설정할 수 없다(2단계 계층 불가). "
            "상위-하위 관계는 같은 프로젝트 안에서만 가능."
        ),
        tags=tag,
    )
    async def dooray_set_parent_post(project_id: str, post_id: str, parent_post_id: str | None = None) -> dict:
        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/set-parent-post",
            data={"parentPostId": parent_post_id},
            keep_data_nulls=("parentPostId",),
        )

    @mcp.tool(
        title="Dooray 업무 이동",
        description=(
            "⚠️ Dooray 에 즉시 반영·비가역. 업무를 다른 프로젝트로 이동한다. "
            "주의: 이동하면 그 업무의 워크플로(단계)·태그 정보는 사라진다. "
            "include_sub_posts=True 면 하위 업무도 함께 이동. target_project_id 는 `dooray_projects` 로 확보."
        ),
        tags=tag,
    )
    async def dooray_move_post(
        project_id: str, post_id: str, target_project_id: str, include_sub_posts: bool = True
    ) -> dict:
        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/posts/{post_id}/move",
            data={"targetProjectId": target_project_id, "includeSubPosts": include_sub_posts},
        )

    @mcp.tool(
        title="Dooray 태그 정의 생성",
        description=(
            "⚠️ Dooray 에 즉시 반영. 프로젝트에 새 태그(정의)를 생성한다. "
            "name 이 `그룹명:태그명` 형식이면 그룹 태그, 그냥 `태그명`이면 개별 태그. color 는 6자리 hex(예: ffffff). "
            "생성된 태그 id 는 이후 업무의 tag_ids 로 사용. "
            "‼️ 주의: 한 번 만든 태그 정의는 이 도구(및 Dooray API)로는 수정·삭제할 수 없다 — "
            "오타/불필요 태그 정리는 오직 Dooray 웹 UI에서 수동으로만 가능하니, 생성 전 name·color 를 신중히 확정할 것."
        ),
        tags=tag,
    )
    async def dooray_add_tag(project_id: str, name: str, color: str = "ffffff") -> dict:
        return await _proxy(
            method="POST",
            dooray_path=f"/project/v1/projects/{project_id}/tags",
            data={"name": name, "color": color},
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
