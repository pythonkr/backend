from fastmcp.exceptions import ToolError


def require_host(domain: str) -> str:
    if host := domain.strip().strip("/").lower():
        return host

    raise ToolError(
        "domain 에 프론트엔드 호스트가 필요합니다 (예: 2026.pycon.kr). 도메인 그룹 목록 도구로 유효한 도메인을 확인하세요."
    )
