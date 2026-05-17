from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp
from core.filter.multi_field import MultiFieldOrCharInFilter
from django_filters import rest_framework as filters


def _social_app_provider_choices() -> list[tuple[str, str]]:
    """SocialApp 에 등록된 provider 만 허용. callable 로 두어 매 요청마다 최신 DB 상태를 반영."""
    return [(p, p) for p in SocialApp.objects.values_list("provider", flat=True).distinct().order_by("provider")]


class SocialAppProviderInFilter(filters.BaseInFilter, filters.ChoiceFilter):
    """CSV 다중값 입력 + SocialApp.provider 화이트리스트 검증 + `__in` 매칭. 각 값을 단일 choice 로 검증.

    `expose_callable_choices_in_schema` 는 `core.openapi.filter_extension.DjangoFilterExtension` 가
    스키마 생성 시 callable choices 를 한 번 호출하도록 opt-in.
    """

    expose_callable_choices_in_schema = True


class SocialAccountAdminFilterSet(filters.FilterSet):
    """admin 운영자 검색. provider 는 SocialApp 에 등록된 값만 허용 (`?provider=google,kakao`)."""

    provider = SocialAppProviderInFilter(field_name="provider", choices=_social_app_provider_choices)
    uid = filters.CharFilter(field_name="uid", lookup_expr="icontains")
    user_email = filters.CharFilter(field_name="user__email", lookup_expr="icontains")
    user_username = filters.CharFilter(field_name="user__username", lookup_expr="icontains")

    date_joined_after = filters.DateTimeFilter(field_name="date_joined", lookup_expr="gte")
    date_joined_before = filters.DateTimeFilter(field_name="date_joined", lookup_expr="lte")
    last_login_after = filters.DateTimeFilter(field_name="last_login", lookup_expr="gte")
    last_login_before = filters.DateTimeFilter(field_name="last_login", lookup_expr="lte")

    class Meta:
        model = SocialAccount
        fields = [
            "user",
            "provider",
            "uid",
            "user_email",
            "user_username",
            "date_joined_after",
            "date_joined_before",
            "last_login_after",
            "last_login_before",
        ]


class EmailAddressAdminFilterSet(filters.FilterSet):
    """`email` 은 EmailAddress.email 과 User.email 양쪽을 OR 매칭. CSV 다중값 지원."""

    email = MultiFieldOrCharInFilter(field_names=["email", "user__email"], lookup_expr="icontains")
    user_username = filters.CharFilter(field_name="user__username", lookup_expr="icontains")

    class Meta:
        model = EmailAddress
        fields = [
            "user",
            "email",
            "verified",
            "primary",
            "user_username",
        ]
