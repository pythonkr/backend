import collections.abc
import re
import typing
import unicodedata

import pandas
from rest_framework import serializers
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.product.models import Option, OptionGroup

MIN_COLUMN_WIDTH = 8
MAX_COLUMN_WIDTH = 50
COLUMN_WIDTH_PADDING = 2

# 한 주문 상품이 같은 옵션 그룹을 여러 번 고른 경우의 2번째 이후 컬럼명 — `검은색 티셔츠 (2)`.
NUMBERED_OPTION_COLUMN = re.compile(r"^(?P<name>.+) \((?P<nth>\d+)\)$")


def _display_width(value: object) -> int:
    # 엑셀 열 너비는 글자 수 기준이라 한글/전각은 두 칸으로 세야 실제 표시 폭에 맞는다.
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(value))


def autofit_columns(worksheet: typing.Any, df: pandas.DataFrame, *, index: bool = True) -> None:
    """헤더/값의 표시 폭에 맞춰 각 열 너비를 지정한다. `engine="xlsxwriter"` 전용."""
    offset = 1 if index else 0
    if index:
        worksheet.set_column(0, 0, MIN_COLUMN_WIDTH)

    for position, column in enumerate(df.columns):
        content_width = max(
            [_display_width(column), *(_display_width(value) for value in df[column].dropna())],
        )
        width = min(max(content_width + COLUMN_WIDTH_PADDING, MIN_COLUMN_WIDTH), MAX_COLUMN_WIDTH)
        worksheet.set_column(position + offset, position + offset, width)


def _option_column_sort_key(column: str) -> tuple[str, int]:
    match = NUMBERED_OPTION_COLUMN.match(column)
    return (match["name"], int(match["nth"])) if match else (column, 1)


def _ordered_columns(df: pandas.DataFrame, fixed_labels: collections.abc.Sequence[str]) -> list[str]:
    """고정 컬럼은 field_def 순서, 옵션 그룹 컬럼은 이름순으로 배치한다.

    옵션 컬럼은 행마다 동적으로 붙어 기본 순서가 "먼저 등장한 순" — 데이터가 바뀌면 열 순서도 바뀌고
    `그룹명 (2)` 가 다른 그룹 뒤로 밀려 수기 집계에서 누락되기 쉽다. (그룹명, n) 정렬로 항상 붙여 둔다.
    """
    present = [str(column) for column in df.columns]
    fixed = [label for label in fixed_labels if label in present]
    dynamic = sorted(set(present) - set(fixed), key=_option_column_sort_key)
    return fixed + dynamic


class ListExportSerializer(serializers.ListSerializer):
    def export(self) -> pandas.DataFrame:
        field_def = self.child.Meta.field_def  # type: ignore[attr-defined,union-attr]
        df = pandas.DataFrame(data=self.data).rename(columns=dict(field_def))
        return df[_ordered_columns(df, [label for _, label in field_def])]


class OrderExportSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email")
    customer_name = serializers.CharField(source="customer_info.name", allow_null=True)
    customer_phone = serializers.CharField(source="customer_info.phone", allow_null=True)
    customer_email = serializers.EmailField(source="customer_info.email", allow_null=True)
    customer_organization = serializers.CharField(source="customer_info.organization", allow_null=True)

    first_paid_at = serializers.DateTimeField()

    class Meta:
        model = Order
        list_serializer_class = ListExportSerializer
        field_def: collections.abc.Sequence[tuple[str, str]] = (
            ("id", "주문 번호"),
            ("user_email", "주문 계정 이메일"),
            ("customer_name", "고객명"),
            ("customer_phone", "고객 전화번호"),
            ("customer_email", "고객 이메일"),
            ("customer_organization", "고객 소속"),
            ("name", "주문명"),
            ("first_paid_at", "첫 결제 시간"),
            ("first_paid_price", "첫 결제 금액"),
            ("current_paid_price", "현재 결제 금액"),
            ("current_status", "현재 상태"),
            ("latest_imp_id", "PortOne ID"),
        )
        fields: list[str] = [field[0] for field in field_def]
        field_names: list[str] = [field[1] for field in field_def]

    def export(self) -> pandas.DataFrame:
        raise NotImplementedError(".export method is implemented in ListExportSerializer")


class OrderProductExportSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")

    class Meta:
        model = OrderProductRelation
        field_def: collections.abc.Sequence[tuple[str, str]] = (
            ("order_id", "주문 번호"),
            ("product_id", "상품 ID"),
            ("product_name", "상품명"),
            ("status", "상태"),
            ("price", "결제 금액"),
            ("donation_price", "추가 기부액"),
        )
        list_serializer_class = ListExportSerializer
        fields: list[str] = [field[0] for field in field_def]
        field_names: list[str] = [field[1] for field in field_def]

    def to_representation(self, instance: OrderProductRelation) -> dict[str, typing.Any]:
        result: dict[str, typing.Any] = super().to_representation(instance)

        options: collections.abc.Iterable[OrderProductOptionRelation] = (
            instance.options.filter_active()
            .select_related("product_option_group", "product_option")
            .order_by("product_option__priority", "created_at", "id")
        )
        seen_per_group: collections.Counter[str] = collections.Counter()
        for option in options:
            option_group: OptionGroup = option.product_option_group
            selected_option: Option | None = option.product_option

            name: str = option_group.name
            value: str | None = (
                option.custom_response
                if option_group.is_custom_response
                else (selected_option.name if selected_option else None)
            )

            seen_per_group[name] += 1
            # 같은 그룹 옵션을 여러 개 고른 주문은 `그룹명`, `그룹명 (2)` … 로 컬럼을 나눈다.
            # 한 키에 덮어쓰면 두 번째부터가 사라져 사이즈별 수량 집계가 어긋난다.
            nth = seen_per_group[name]
            result[name if nth == 1 else f"{name} ({nth})"] = value

        return result

    def export(self) -> pandas.DataFrame:
        raise NotImplementedError(".export method is implemented in ListExportSerializer")
