from urllib.parse import urljoin

from core.const.google_api import GOOGLE_OAUTH2_AUTH_URI, GOOGLE_OAUTH2_TOKEN_INFO_URI, GOOGLE_OAUTH2_TOKEN_URI
from django.conf import settings
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from httpx import get as httpx_get
from httpx import post as httpx_post
from rest_framework.reverse import reverse


def create_oauth_flow() -> Flow | None:
    if not all(getattr(settings.GOOGLE_CLOUD, attr) for attr in ("CLIENT_ID", "CLIENT_SECRET", "SCOPES")):
        return None

    return Flow.from_client_config(
        client_config={
            "web": {
                "auth_uri": GOOGLE_OAUTH2_AUTH_URI,
                "token_uri": GOOGLE_OAUTH2_TOKEN_URI,
                "client_id": settings.GOOGLE_CLOUD.CLIENT_ID,
                "client_secret": settings.GOOGLE_CLOUD.CLIENT_SECRET,
            },
        },
        scopes=settings.GOOGLE_CLOUD.SCOPES,
        redirect_uri=urljoin(settings.BACKEND_DOMAIN, reverse("v1:google-oauth2-redirect")),
    )


def create_authorization_url(
    flow: Flow, prompt: str = "consent", access_type: str = "offline", include_granted_scopes: bool = False
) -> tuple[str, str | None, str]:
    url, state = flow.authorization_url(
        prompt=prompt,
        access_type=access_type,
        include_granted_scopes="true" if include_granted_scopes else "false",
    )
    return url, flow.code_verifier, state


def fetch_credentials(flow: Flow, code: str) -> Credentials:
    flow.fetch_token(code=code)
    return flow.credentials


def create_credentials(refresh_token: str) -> Credentials:
    return Credentials.from_authorized_user_info(
        {
            "refresh_token": refresh_token,
            "client_id": settings.GOOGLE_CLOUD.CLIENT_ID,
            "client_secret": settings.GOOGLE_CLOUD.CLIENT_SECRET,
        }
    )


def fetch_access_token(refresh_token: str, timeout: float = 10.0) -> dict:
    return (
        httpx_post(
            url=GOOGLE_OAUTH2_TOKEN_URI,
            data={
                "client_id": settings.GOOGLE_CLOUD.CLIENT_ID,
                "client_secret": settings.GOOGLE_CLOUD.CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=timeout,
        )
        .raise_for_status()
        .json()
    )


def fetch_token_info(access_token: str, timeout: float = 10.0) -> dict:
    return (
        httpx_get(url=GOOGLE_OAUTH2_TOKEN_INFO_URI, params={"access_token": access_token}, timeout=timeout)
        .raise_for_status()
        .json()
    )
