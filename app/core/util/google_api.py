from urllib.parse import urljoin

from core.const.google_api import GOOGLE_OAUTH2_AUTH_URI, GOOGLE_OAUTH2_TOKEN_URI
from django.conf import settings
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
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
        redirect_uri=urljoin(settings.BACKEND_DOMAIN, reverse("v1:google-oauth2-authorize")),
    )


def create_authorization_url(
    flow: Flow, prompt: str = "consent", access_type: str = "offline", include_granted_scopes: bool = False
) -> str:
    return flow.authorization_url(
        prompt=prompt,
        access_type=access_type,
        include_granted_scopes="true" if include_granted_scopes else "false",
    )[0]


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
