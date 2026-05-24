"""OpenAPI 스키마에서 leftover_stock_info 의 키들이 명시화 됐는지 회귀 가드.

`@extend_schema_field` 가 빠지면 dict 가 `additionalProperties: {type: integer, nullable: true}` 로
빠져서 키들이 schema 에 사라진다. 프론트 codegen 이 깨지므로 명시 누락을 이 테스트로 막는다.
"""

import pytest
import yaml
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_option_dto_leftover_stock_info_has_explicit_keys():
    response = APIClient().get("/api/schema/v1/")
    schemas = yaml.safe_load(response.content)["components"]["schemas"]

    option_info = schemas["OptionLeftoverStockInfo"]
    assert set(option_info["properties"]) == {
        "product_max_quantity_per_user",
        "product_leftover_stock",
        "option_group_max_quantity_per_user",
        "option_max_quantity_per_user",
        "option_leftover_stock",
    }
    for prop in option_info["properties"].values():
        assert prop == {"type": "integer", "nullable": True}

    group_info = schemas["OptionGroupLeftoverStockInfo"]
    assert set(group_info["properties"]) == {
        "product_max_quantity_per_user",
        "product_leftover_stock",
        "option_group_max_quantity_per_user",
    }

    # DTO 의 leftover_stock_info 필드가 위 컴포넌트를 참조해야 한다 ($ref).
    assert schemas["OptionDto"]["properties"]["leftover_stock_info"] == {
        "allOf": [{"$ref": "#/components/schemas/OptionLeftoverStockInfo"}],
        "readOnly": True,
    }
    assert schemas["OptionGroupDto"]["properties"]["leftover_stock_info"] == {
        "allOf": [{"$ref": "#/components/schemas/OptionGroupLeftoverStockInfo"}],
        "readOnly": True,
    }
