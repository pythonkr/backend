import pytest
from django.contrib.auth import SESSION_KEY
from django.urls import reverse
from user.models import UserExt


@pytest.fixture
def user(db) -> UserExt:
    return UserExt.objects.create_user(username="u", email="u@example.com")


def test_account_home_shows_logout_button(client, user):
    client.force_login(user)

    response = client.get(reverse("account-home"))

    assert response.status_code == 200
    assert reverse("account-logout").encode() in response.content


def test_logout_clears_session_and_redirects(client, user):
    client.force_login(user)
    assert SESSION_KEY in client.session

    response = client.post(reverse("account-logout"))

    assert response.status_code == 302
    assert response.url == reverse("account-login")
    assert SESSION_KEY not in client.session


def test_logout_rejects_get(client, user):
    client.force_login(user)

    response = client.get(reverse("account-logout"))

    assert response.status_code == 405
