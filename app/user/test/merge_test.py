from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from core.util.thread_local import thread_local
from django.contrib.contenttypes.models import ContentType
from shop.order.models import Order
from user.models import UserExt
from user.models.mcp_token import McpToken
from user.models.merge import UserMergeHistory, UserMergeObject
from user.models.organization import Organization, OrganizationUserRelation


@pytest.fixture
def source_user(db) -> UserExt:
    return UserExt.objects.create_user(username="source", email="source@example.com")


@pytest.fixture
def target_user(db) -> UserExt:
    return UserExt.objects.create_user(username="target", email="target@example.com")


@pytest.fixture
def actor_user(db) -> UserExt:
    return UserExt.objects.create_superuser(username="admin", email="admin@example.com")


@contextmanager
def _acting_as(user):
    """created_by 는 get_current_user()(thread-local)에서 잡히므로, 실행자를 테스트에서 명시하려면 여기서 주입."""
    if user is not None:
        thread_local.current_request = SimpleNamespace(user=user)
    try:
        yield
    finally:
        if hasattr(thread_local, "current_request"):
            del thread_local.current_request


def _merge(source, target, actor=None) -> UserMergeHistory:
    with _acting_as(actor):
        history = UserMergeHistory.objects.create(source=source, target=target)  # created_by=actor
    history.merge()
    return history


def test_merge_repoints_owned_business_fk(source_user, target_user):
    order = Order.objects.create(user=source_user, name="src-order")

    _merge(source_user, target_user)

    order.refresh_from_db()
    assert order.user_id == target_user.id


def test_merge_deactivates_source_and_sets_merged_to(source_user, target_user):
    merge = _merge(source_user, target_user)

    source_user.refresh_from_db()
    assert source_user.is_active is False
    assert source_user.merged_to_id == target_user.id
    assert merge.source_id == source_user.id and merge.target_id == target_user.id


def test_merge_records_moved_objects(source_user, target_user):
    order = Order.objects.create(user=source_user, name="src-order")

    merge = _merge(source_user, target_user)

    order_ct = ContentType.objects.get_for_model(Order)
    recorded = UserMergeObject.objects.get(history=merge, target_type=order_ct, target_id=str(order.id))
    assert recorded.field_names == ["user"]


def test_tracked_model_gets_history_with_change_reason(source_user, target_user, actor_user):
    order = Order.objects.create(user=source_user, name="src-order")

    merge = _merge(source_user, target_user, actor=actor_user)

    update_record = order.history.filter(history_type="~").order_by("-history_date", "-history_id").first()
    assert update_record is not None
    assert update_record.user_id == target_user.id
    assert update_record.history_change_reason == f"account_merge:{merge.pk}"
    assert update_record.history_user_id == actor_user.id


def test_untracked_model_is_repointed(source_user, target_user):
    org = Organization.objects.create(name="Acme")
    relation = OrganizationUserRelation.objects.create(organization=org, user=source_user)

    _merge(source_user, target_user)

    relation.refresh_from_db()
    assert relation.user_id == target_user.id


def test_allauth_accounts_are_moved(source_user, target_user):
    SocialAccount.objects.create(user=source_user, provider="google", uid="src-google", extra_data={})
    EmailAddress.objects.create(user=source_user, email="source@example.com", verified=True, primary=True)

    _merge(source_user, target_user)

    assert SocialAccount.objects.filter(user=target_user, uid="src-google").exists()
    assert EmailAddress.objects.filter(user=target_user, email="source@example.com").exists()


def test_mcp_token_is_moved(source_user, target_user):
    token = McpToken.objects.create(user=source_user)

    _merge(source_user, target_user)

    token.refresh_from_db()
    assert token.user_id == target_user.id


def test_audit_fields_are_not_moved(source_user, target_user):
    """created_by(=authorship) 는 이관하지 않는다 — 병합 후에도 source 를 가리켜야 함."""
    org = Organization.objects.create(name="Acme")
    Organization.objects.filter(pk=org.pk).update(created_by=source_user)

    _merge(source_user, target_user)

    org.refresh_from_db()
    assert org.created_by_id == source_user.id


def test_source_email_moves_and_demotes_when_target_has_primary(source_user, target_user):
    """target 이 이미 primary 를 가지면, source 의 (중복 아닌) 이메일은 source 에 남기지 않고 target 으로
    옮기며 primary 를 강등한다 — 죽은 계정에 주소가 갇히지 않게."""
    EmailAddress.objects.create(user=source_user, email="source@example.com", verified=True, primary=True)
    EmailAddress.objects.create(user=target_user, email="target@example.com", verified=True, primary=True)

    _merge(source_user, target_user)

    assert not EmailAddress.objects.filter(user=source_user).exists()
    assert EmailAddress.objects.filter(user=target_user, primary=True).count() == 1
    moved = EmailAddress.objects.get(user=target_user, email="source@example.com")
    assert moved.primary is False and moved.verified is True


def test_duplicate_email_consolidates_verification_and_demotes_source(source_user, target_user):
    """양쪽이 같은 주소를 가지면 삭제 없이: target 사본을 verified 로 승격하고 source 사본은 미검증으로 강등해 남긴다."""
    EmailAddress.objects.create(user=source_user, email="dup@example.com", verified=True, primary=True)
    EmailAddress.objects.create(user=target_user, email="dup@example.com", verified=False, primary=False)
    EmailAddress.objects.create(user=target_user, email="target@example.com", verified=True, primary=True)

    _merge(source_user, target_user)

    assert EmailAddress.objects.get(user=target_user, email="dup@example.com").verified is True
    source_dup = EmailAddress.objects.get(user=source_user, email="dup@example.com")
    assert source_dup.verified is False  # 삭제 아님, 강등돼 잔류


def test_target_primary_assigned_when_missing(source_user, target_user):
    """규칙3: 병합 후 target 에 primary 가 없으면 하나(verified 우선)를 지정한다."""
    EmailAddress.objects.create(user=target_user, email="target@example.com", verified=True, primary=False)

    _merge(source_user, target_user)

    assert EmailAddress.objects.filter(user=target_user, primary=True).count() == 1
    target_user.refresh_from_db()
    assert target_user.email == "target@example.com"  # set_as_primary 가 UserExt.email 동기화


def test_unmerge_restores_email_state(source_user, target_user):
    """규칙1(옮김+강등)·규칙2(검증통합) 모두 before-image replay 로 정확히 복원된다."""
    EmailAddress.objects.create(user=source_user, email="source@example.com", verified=True, primary=True)
    EmailAddress.objects.create(user=source_user, email="dup@example.com", verified=True, primary=False)
    EmailAddress.objects.create(user=target_user, email="dup@example.com", verified=False, primary=False)
    EmailAddress.objects.create(user=target_user, email="target@example.com", verified=True, primary=True)

    merge = _merge(source_user, target_user)
    merge.unmerge()

    src_primary = EmailAddress.objects.get(user=source_user, email="source@example.com")
    assert src_primary.primary is True and src_primary.verified is True
    assert EmailAddress.objects.get(user=source_user, email="dup@example.com").verified is True
    assert EmailAddress.objects.get(user=target_user, email="dup@example.com").verified is False
    assert not EmailAddress.objects.filter(user=target_user, email="source@example.com").exists()


def test_unmerge_rejected_when_target_later_merged(source_user, target_user):
    """forward chain: A→B 후 B→C 이면, B.merged_to 가 채워져 A→B 를 먼저 되돌릴 수 없다(LIFO)."""
    c = UserExt.objects.create_user(username="c2", email="c2@example.com")
    first = _merge(source_user, target_user)
    _merge(target_user, c)

    with pytest.raises(ValueError):
        first.unmerge()


def test_chain_is_flattened_to_depth_one(target_user):
    """B→A 병합 후 A→C 병합 시, B 는 A 가 아니라 최종 C 를 직접 가리켜야 한다."""
    b = UserExt.objects.create_user(username="b", email="b@example.com")
    a = UserExt.objects.create_user(username="a", email="a@example.com")
    c = target_user

    _merge(b, a)
    _merge(a, c)

    b.refresh_from_db()
    a.refresh_from_db()
    assert a.merged_to_id == c.id
    assert b.merged_to_id == c.id  # 평탄화 — depth 1


def test_prior_merge_record_not_rewritten(source_user, target_user):
    """UserMergeHistory.source/target 은 sweep 대상이 아니어야 — 후속 병합이 과거 기록을 재작성하면 안 됨."""
    c = UserExt.objects.create_user(username="c", email="c@example.com")
    first = _merge(source_user, target_user)
    _merge(target_user, c)  # target 을 다시 source 로 병합

    first.refresh_from_db()
    assert first.target_id == target_user.id and first.source_id == source_user.id


def test_unmerge_restores_objects_and_source(source_user, target_user):
    order = Order.objects.create(user=source_user, name="src-order")
    merge = _merge(source_user, target_user)

    merge.unmerge()

    order.refresh_from_db()
    source_user.refresh_from_db()
    merge.refresh_from_db()
    assert order.user_id == source_user.id
    assert source_user.is_active is True
    assert source_user.merged_to_id is None
    assert merge.reverted_at is not None


# ---- method 파생 (is_self_merge) --------------------------------------------


def test_is_self_merge_true_when_actor_is_target(source_user, target_user):
    merge = _merge(source_user, target_user, actor=target_user)

    assert merge.is_self_merge is True


def test_is_self_merge_false_for_operator(source_user, target_user, actor_user):
    merge = _merge(source_user, target_user, actor=actor_user)

    assert merge.is_self_merge is False


# ---- guards ------------------------------------------------------------------


def test_merge_same_user_rejected(source_user):
    with pytest.raises(ValueError):
        _merge(source_user, source_user)


def test_merge_into_already_merged_target_rejected(source_user, target_user):
    other = UserExt.objects.create_user(username="c", email="c@example.com")
    _merge(target_user, other)  # target 이 이미 병합됨

    with pytest.raises(ValueError):
        _merge(source_user, target_user)


def test_merge_already_merged_source_rejected(source_user, target_user):
    other = UserExt.objects.create_user(username="c", email="c@example.com")
    _merge(source_user, other)  # source 가 이미 병합됨

    with pytest.raises(ValueError):
        _merge(source_user, target_user)


def test_double_unmerge_rejected(source_user, target_user):
    merge = _merge(source_user, target_user)
    merge.unmerge()

    with pytest.raises(ValueError):
        merge.unmerge()


# ---- assert_self_mergeable (본인 병합 사전검증) --------------------------------


def _verified_email(user, email):
    return EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)


def test_self_mergeable_passes_when_both_verified(source_user, target_user):
    _verified_email(source_user, "source@example.com")
    _verified_email(target_user, "target@example.com")

    UserMergeHistory.assert_self_mergeable(source_user, target_user)  # no raise


def test_self_mergeable_allows_email_less_source(source_user, target_user):
    _verified_email(target_user, "target@example.com")  # source 는 이메일 없음 → 허용

    UserMergeHistory.assert_self_mergeable(source_user, target_user)  # no raise


def test_self_mergeable_rejects_email_less_target(source_user, target_user):
    _verified_email(source_user, "source@example.com")

    with pytest.raises(ValueError):
        UserMergeHistory.assert_self_mergeable(source_user, target_user)


def test_self_mergeable_rejects_unverified_target_email(source_user, target_user):
    _verified_email(source_user, "source@example.com")
    _verified_email(target_user, "target@example.com")
    EmailAddress.objects.create(user=target_user, email="extra@example.com", verified=False)

    with pytest.raises(ValueError):
        UserMergeHistory.assert_self_mergeable(source_user, target_user)


def test_self_mergeable_rejects_unverified_source_email(source_user, target_user):
    _verified_email(target_user, "target@example.com")
    EmailAddress.objects.create(user=source_user, email="source@example.com", verified=False)

    with pytest.raises(ValueError):
        UserMergeHistory.assert_self_mergeable(source_user, target_user)
