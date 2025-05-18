from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter


class BackendAutoSchema(AutoSchema):
    global_params = [
        OpenApiParameter(
            name="Accept-Language", location=OpenApiParameter.HEADER, description="`ko` or `en`. Default value is `ko`"
        )
    ]

    def get_override_parameters(self) -> list[OpenApiParameter]:
        return super().get_override_parameters() + self.global_params
