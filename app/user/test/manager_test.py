import pytest
from allauth.account.models import EmailAddress
from user.models import UserExt


@pytest.fixture
def user(db) -> UserExt:
    return UserExt.objects.create_user(username="buyer", email="buyer@example.com")


@pytest.mark.django_db
def test_filter_by_email_matches_primary_and_secondary_addresses(user):
    EmailAddress.objects.create(user=user, email="alt@example.com", verified=True)
    assert list(UserExt.objects.filter_by_email("buyer@example.com")) == [user]
    assert list(UserExt.objects.filter_by_email(" ALT@example.com ")) == [user]


@pytest.mark.django_db
def test_filter_by_email_falls_back_to_user_email_column(user):
    # EmailAddress 백필 이전에 만들어진 계정 — allauth 레코드 없이 User.email 만 있는 경우.
    EmailAddress.objects.filter(user=user).delete()
    assert list(UserExt.objects.filter_by_email("buyer@example.com")) == [user]


@pytest.mark.django_db
def test_filter_by_email_returns_empty_for_unknown_or_blank(user):
    assert not UserExt.objects.filter_by_email("nobody@example.com").exists()
    assert not UserExt.objects.filter_by_email("").exists()


@pytest.mark.django_db
def test_get_or_create_by_email_returns_existing_account(user):
    EmailAddress.objects.create(user=user, email="alt@example.com", verified=True)
    assert UserExt.objects.get_or_create_by_email("alt@example.com") == (user, False)


@pytest.mark.django_db
def test_get_or_create_by_email_resolves_merged_account_to_target(user):
    merged = UserExt.objects.create_user(username="merged", email="merged@example.com")
    merged.merged_to = user
    merged.is_active = False
    merged.save(update_fields=["merged_to", "is_active"])
    assert UserExt.objects.get_or_create_by_email("merged@example.com") == (user, False)


@pytest.mark.django_db
def test_get_or_create_by_email_prefers_verified_address_owner(user):
    unverified_owner = UserExt.objects.create_user(username="unverified", email="other@example.com")
    EmailAddress.objects.create(user=unverified_owner, email="shared@example.com", verified=False)
    EmailAddress.objects.create(user=user, email="shared@example.com", verified=True)
    assert UserExt.objects.get_or_create_by_email("shared@example.com") == (user, False)


@pytest.mark.django_db
def test_get_or_create_by_email_creates_verified_account_without_password(db):
    created, is_created = UserExt.objects.get_or_create_by_email(
        " Nobody@Example.com ", nickname_ko="홍길동", nickname_en="Gildong"
    )
    assert is_created
    assert created.email == "nobody@example.com"
    assert created.username == "nobody"
    assert (created.nickname_ko, created.nickname_en) == ("홍길동", "Gildong")
    assert not created.has_usable_password()
    assert EmailAddress.objects.filter(user=created, email="nobody@example.com", verified=True, primary=True).exists()


@pytest.mark.django_db
def test_create_by_email_prefixes_domain_on_username_collision(db):
    UserExt.objects.create_user(username="nobody", email="other@example.com")
    created = UserExt.objects.create_by_email("nobody@example.com")
    assert created.username == "example.com-nobody"
    assert created.email == "nobody@example.com"


@pytest.mark.django_db
def test_create_by_email_appends_random_suffix_when_domain_prefix_also_taken(db):
    UserExt.objects.create_user(username="nobody", email="other@example.com")
    UserExt.objects.create_user(username="example.com-nobody", email="another@example.com")
    created = UserExt.objects.create_by_email("nobody@example.com")
    assert created.username.startswith("example.com-nobody-")
    assert created.email == "nobody@example.com"


@pytest.mark.django_db
def test_create_by_email_passes_create_user_arguments_through(db):
    created = UserExt.objects.create_by_email(
        "staff@example.com", "s3cret", username="staff", is_superuser=True, nickname_ko="스태프"
    )
    assert (created.username, created.is_superuser, created.nickname_ko) == ("staff", True, "스태프")
    assert created.check_password("s3cret")
