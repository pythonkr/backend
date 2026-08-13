from rest_framework import negotiation, parsers, renderers, request


class IgnoreClientContentNegotiation(negotiation.BaseContentNegotiation):
    """클라이언트의 Accept 헤더를 무시하고 뷰의 첫 렌더러를 강제한다.
    QR 스캐너 인앱 브라우저처럼 Accept 를 이상하게 보내는 클라이언트에게 406 대신 정상 응답을 돌려주기 위함.
    """

    def select_parser(self, request: request.Request, parsers_: list[parsers.BaseParser]) -> parsers.BaseParser | None:
        return parsers_[0] if parsers_ else None

    def select_renderer(
        self,
        request: request.Request,
        renderers_: list[renderers.BaseRenderer],
        format_suffix: str | None = None,
    ) -> tuple[renderers.BaseRenderer, str]:
        return renderers_[0], renderers_[0].media_type
