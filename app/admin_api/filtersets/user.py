from django_filters import rest_framework as filters
from user.models import UserExt


class UserAdminFilterSet(filters.FilterSet):
    username = filters.CharFilter(lookup_expr="icontains")
    email = filters.CharFilter(lookup_expr="icontains")
    nickname = filters.CharFilter(lookup_expr="icontains")
    date_joined_after = filters.DateTimeFilter(field_name="date_joined", lookup_expr="gte")
    date_joined_before = filters.DateTimeFilter(field_name="date_joined", lookup_expr="lte")

    class Meta:
        model = UserExt
        fields = [
            "username",
            "email",
            "nickname",
            "is_staff",
            "is_superuser",
            "date_joined_after",
            "date_joined_before",
        ]
