import pytest
import yaml
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_create_single_product_order_response_schema_is_not_ambiguous_oneof():
    response = APIClient().get("/api/schema/v1/")
    assert response.status_code == 200

    schema = yaml.safe_load(response.content)
    path = next(path for path in schema["paths"] if path.endswith("/shop/orders/single/"))
    response_schema = schema["paths"][path]["post"]["responses"]["201"]["content"]["application/json"]["schema"]

    assert response_schema == {"$ref": "#/components/schemas/CreateSingleProductOrderResponseDto"}
    assert "oneOf" not in schema["components"]["schemas"]["CreateSingleProductOrderResponseDto"]
