from __future__ import annotations

import re
from dataclasses import dataclass

from fastmcp.server.providers.openapi import MCPType, RouteMap

from mcp_app.auth import ADMIN_TAG

_ADMIN = {ADMIN_TAG}


@dataclass(frozen=True, kw_only=True)
class Route:
    method: str
    path: str  # spec 의 정확한 경로(예: /v1/admin-api/cms/page/{id}/)
    summary: str  # 도구 표시명(title)
    description: str = ""  # LLM 이 읽는 본문
    admin: bool = True  # 어드민(슈퍼유저) 전용 여부

    @property
    def route_map(self) -> RouteMap:
        return RouteMap(
            pattern=rf"^{re.escape(self.path)}$",
            methods=[self.method],
            mcp_type=MCPType.TOOL,
            mcp_tags=_ADMIN if self.admin else set(),
        )


ROUTES: list[Route] = [
    # ── CMS 도메인 그룹(어드민 읽기) ──
    Route(
        method="GET",
        path="/v1/admin-api/cms/domain-group/",
        summary="도메인 그룹 목록",
        description="프론트엔드 도메인 그룹(name + domains 호스트 목록)을 조회합니다. "
        "CMS 페이지/사이트맵의 domain_group 이 어떤 실제 도메인(예: 2026.pycon.kr)에 대응하는지 확인하고, "
        "그 도메인을 mdx_components 도구의 domain 인자로 넣어 사용 가능한 MDX 컴포넌트를 확인하세요.",
    ),
    # ── CMS 사이트맵(어드민 쓰기) ──
    Route(
        method="GET",
        path="/v1/admin-api/cms/sitemap/",
        summary="사이트맵 목록",
        description="사이트맵(메뉴 트리 노드)을 조회합니다. domain_group 으로 필터할 수 있습니다.",
    ),
    Route(
        method="POST",
        path="/v1/admin-api/cms/sitemap/",
        summary="사이트맵 생성",
        description="새 사이트맵 노드를 만듭니다. ⚠️ 생성 즉시 외부 공개 — `https://<도메인>/<route>` 로 접근 가능합니다"
        "(route=부모 route_code 체인+이 노드의 route_code, 도메인=domain_group.domains; hide=true 또는 display 기간 밖이면 숨김). "
        "route_code 는 알파벳·숫자·`_`·`-` 만 사용하고 도메인 그룹 내에서 유일해야 합니다. "
        "관계 필드는 choices 도구로 유효 id 를 확인하세요.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/cms/sitemap/{id}/",
        summary="사이트맵 상세",
    ),
    Route(
        method="PATCH",
        path="/v1/admin-api/cms/sitemap/{id}/",
        summary="사이트맵 수정",
        description="사이트맵 필드를 부분 수정합니다. ⚠️ 변경 즉시 외부 반영 — "
        "route_code/parent/hide/display 수정은 공개 URL·노출을 바로 바꿉니다.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/cms/sitemap/choices/",
        summary="사이트맵 관계 선택지",
        description="FK/M2M 필드의 유효한 선택지(const=id, title=표시명). 관계 값을 채우기 전에 호출하세요.",
    ),
    # ── CMS 페이지(어드민 쓰기) ──
    Route(
        method="GET",
        path="/v1/admin-api/cms/page/",
        summary="페이지 목록",
        description="페이지를 조회/필터합니다(페이지네이션 count/results).",
    ),
    Route(
        method="POST",
        path="/v1/admin-api/cms/page/",
        summary="페이지 생성",
        description="새 페이지를 만듭니다. ⚠️ 생성 즉시 외부 공개 — 프론트엔드의 `https://<도메인>/pages/{생성된 id}` 로 "
        "누구나 접근 가능합니다(네비게이션 노출은 사이트맵 노드가 이 페이지를 연결해야 함). "
        "관계 필드는 choices 도구로 유효 id 를 확인하세요.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/cms/page/{id}/",
        summary="페이지 상세",
    ),
    Route(
        method="PATCH",
        path="/v1/admin-api/cms/page/{id}/",
        summary="페이지 수정",
        description="페이지 필드를 부분 수정합니다. ⚠️ 변경 즉시 외부 공개 페이지에 반영됩니다. "
        "본문 섹션은 section/bulk-update 로 따로 관리합니다.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/cms/page/{id}/section/",
        summary="페이지 섹션 목록",
        description="페이지의 섹션을 순서대로 조회합니다. bulk-update 전에 현재 상태 확인용으로 호출하세요.",
    ),
    Route(
        method="PUT",
        path="/v1/admin-api/cms/page/{id}/section/bulk-update/",
        summary="페이지 섹션 일괄 교체",
        description="페이지 섹션(=공개 페이지 본문) 전체를 한 번에 교체합니다. ⚠️ 변경 즉시 외부 반영. "
        '본문: {"sections": [{"order": 0, "body_ko": "...", "body_en": "..."}]} (기존 섹션을 유지하려면 그 id 도 포함). '
        "요청 목록에 없는 기존 섹션은 삭제되므로, 먼저 GET section 으로 읽고 유지할 섹션까지 모두 포함해 보내세요. "
        "MDX 본문은 가능한 한 순수 마크다운으로 작성하고, JSX·컴포넌트는 마크다운으로 표현이 안 되는 경우에만 최소한으로 써서 가장 짧은 코드로 구현하세요.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/cms/page/choices/",
        summary="페이지 관계 선택지",
        description="FK/M2M 필드의 유효한 선택지(const=id, title=표시명). 관계 값을 채우기 전에 호출하세요.",
    ),
    # ── 대시보드 통계(어드민 읽기) ──
    Route(
        method="GET",
        path="/v1/admin-api/dashboard/charts/",
        summary="대시보드 차트 목록",
        description="사용 가능한 통계 차트 목록. 각 차트의 id·필요 파라미터 정의(params)·유효 event 옵션(events)을 반환합니다. "
        "차트 데이터 조회 전에 먼저 호출하세요.",
    ),
    Route(
        method="POST",
        path="/v1/admin-api/dashboard/charts/{id}/data/",
        summary="차트 데이터 조회",
        description="특정 차트의 집계 데이터를 조회합니다(읽기). 먼저 '대시보드 차트 목록'에서 차트 id·필요 파라미터·유효 event_id 를 확인하세요. "
        '본문: {"params": {"date_range": {"date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}, '
        '"event_id": "<id>", "granularity": "day|week|month"}} '
        "— 차트마다 필요한 키는 목록의 params 정의를 따릅니다.",
    ),
    # ── 쇼핑 주문·상품(어드민 읽기 전용) ──
    Route(
        method="GET",
        path="/v1/admin-api/shop/category-groups/",
        summary="카테고리 그룹 목록",
        description='티켓 카테고리 그룹(예: "2024"/"2025"/"2026") 목록(id+이름). '
        "여기서 얻은 id 로 상품/주문을 category_group 으로 필터해 연도를 구분하세요.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/orders/",
        summary="주문 목록",
        description="주문을 조회/필터합니다(읽기 전용, 페이지네이션 count/results). 연도 구분은 category_group=<그룹 id> 로.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/orders/{id}/",
        summary="주문 상세",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/products/",
        summary="상품 목록",
        description="상품을 조회/필터합니다(읽기 전용). 연도 구분은 category_group=<그룹 id> 로.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/products/{id}/",
        summary="상품 상세",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/products/choices/",
        summary="상품 관계 선택지",
        description="상품의 FK/M2M 선택지(category, tag 등; const=id, title=표시명). category id 로 상품/주문을 필터할 수 있습니다.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/categories/",
        summary="카테고리 목록",
        description="카테고리 목록(id, 이름, group, event, is_ticket). group/event/is_ticket 으로 필터 가능. "
        "상품/주문을 category=<id> 로 필터할 때 id 출처.",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/categories/{id}/",
        summary="카테고리 상세",
    ),
    Route(
        method="GET",
        path="/v1/admin-api/shop/categories/choices/",
        summary="카테고리 관계 선택지",
        description="카테고리의 FK 선택지: group(카테고리 그룹=연도)·event(const=id, title=표시명).",
    ),
    # ── 행사 정보(공개 읽기) ──
    Route(
        method="GET",
        path="/v1/event/",
        summary="이벤트(연도) 목록",
        description="공개 이벤트 목록(최신 우선). 후원사/발표 도구의 event 필터에 넣을 이름을 여기서 확인하세요. "
        "event 를 생략하면 최신 이벤트가 기본 적용됩니다.",
        admin=False,
    ),
    Route(
        method="GET",
        path="/v1/event/sponsor/",
        summary="후원사 목록",
        description="공개 후원사 목록. event(이벤트 이름)로 연도 필터, 생략 시 최신 이벤트 기본. "
        "특정 event 결과가 비어 있으면 해당 행사의 후원사 정보가 아직 준비 중이라는 뜻입니다(오류 아님).",
        admin=False,
    ),
    Route(
        method="GET",
        path="/v1/event/presentation/",
        summary="발표 목록",
        description="공개 발표 목록. event(이벤트 이름)로 연도 필터(생략 시 최신), types(타입 이름)로도 필터. "
        "특정 event 결과가 비어 있으면 해당 행사의 세션 정보가 아직 준비 중이라는 뜻입니다(오류 아님).",
        admin=False,
    ),
    Route(
        method="GET",
        path="/v1/event/presentation/{id}/",
        summary="발표 상세",
        admin=False,
    ),
]

# allowlist + deny-by-default catch-all(맨 끝 필수).
ROUTE_MAPS: list[RouteMap] = [r.route_map for r in ROUTES] + [RouteMap(pattern=r".*", mcp_type=MCPType.EXCLUDE)]
ROUTE_DOCS: dict[tuple[str, str], Route] = {(r.method, r.path): r for r in ROUTES}


def lookup(method: str, path: str) -> Route | None:
    return ROUTE_DOCS.get((method.upper(), path))
