import pytest
from core.const.shop_error_messages import PermissionErrorMessages
from django.test import override_settings
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from rest_framework.test import APIClient
from shop.test.helpers import valid_refund_totp

_SETUP_QR_URL_NAME = "v1:admin-shop-refund-authorizer-setup-qr"
_VERIFY_URL_NAME = "v1:admin-shop-refund-authorizer-verify"


@pytest.mark.parametrize(
    ("is_local", "debug", "expected_issuer_prefix"),
    [
        (True, True, "PyConKR%3ALocal"),
        (False, True, "PyConKR%3ADev"),
        (False, False, "PyConKR%3AProd"),
    ],
)
@pytest.mark.django_db
def test_setup_qr_uses_environment_specific_issuer(api_client, is_local, debug, expected_issuer_prefix):
    with override_settings(IS_LOCAL=is_local, DEBUG=debug):
        response = api_client.get(reverse(_SETUP_QR_URL_NAME))
    assert response.status_code == HTTP_200_OK
    assert response.json()["otpauth_url"].startswith(f"otpauth://totp/{expected_issuer_prefix}")


@pytest.mark.django_db
def test_setup_qr_requires_superuser(customer_user):
    client = APIClient()
    client.force_authenticate(user=customer_user)
    response = client.get(reverse(_SETUP_QR_URL_NAME))
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_setup_qr_rejects_unauthenticated_request():
    response = APIClient().get(reverse(_SETUP_QR_URL_NAME))
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_verify_returns_valid_true_for_correct_otp(api_client):
    response = api_client.post(reverse(_VERIFY_URL_NAME) + f"?otp={valid_refund_totp()}")
    assert response.status_code == HTTP_200_OK
    assert response.json() == {"valid": True}


@pytest.mark.django_db
def test_verify_returns_valid_false_for_incorrect_otp(api_client):
    response = api_client.post(reverse(_VERIFY_URL_NAME) + "?otp=000000")
    assert response.status_code == HTTP_200_OK
    assert response.json() == {"valid": False}


@pytest.mark.django_db
def test_verify_rejects_missing_otp_with_400(api_client):
    response = api_client.post(reverse(_VERIFY_URL_NAME))
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": PermissionErrorMessages.OTP_REQUIRED}


@pytest.mark.django_db
def test_verify_requires_superuser(customer_user):
    client = APIClient()
    client.force_authenticate(user=customer_user)
    response = client.post(reverse(_VERIFY_URL_NAME) + f"?otp={valid_refund_totp()}")
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_verify_rejects_unauthenticated_request():
    response = APIClient().post(reverse(_VERIFY_URL_NAME) + "?otp=000000")
    assert response.status_code == HTTP_403_FORBIDDEN
