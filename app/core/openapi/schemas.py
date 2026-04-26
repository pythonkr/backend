from drf_spectacular.openapi import AutoSchema, OpenApiExample, OpenApiResponse
from drf_spectacular.utils import OpenApiParameter
from rest_framework import status

HTML_EXAMPLE_STR = "<!DOCTYPE html><html><body><img src='data:image/png;base64, ...'></body></html>"


class BackendAutoSchema(AutoSchema):
    global_params = [
        OpenApiParameter(
            name="Accept-Language", location=OpenApiParameter.HEADER, description="`ko` or `en`. Default value is `ko`"
        )
    ]

    def get_override_parameters(self) -> list[OpenApiParameter]:
        return super().get_override_parameters() + self.global_params


def build_html_responses(names: list[str], status_code: int = status.HTTP_200_OK) -> dict[int, OpenApiResponse]:
    examples = [
        OpenApiExample(
            name=name,
            media_type="text/html",
            value=HTML_EXAMPLE_STR,
            status_codes=[status_code],
        )
        for name in names
    ]
    return {status_code: OpenApiResponse(response=str, examples=examples)}
