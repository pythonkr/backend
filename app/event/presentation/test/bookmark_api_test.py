import http
import uuid
from datetime import datetime

import pytest
from django.urls import reverse
from event.models import Event
from event.presentation.models import Presentation, PresentationBookmark, PresentationType
from model_bakery import baker
from rest_framework.test import APIClient
from user.models.organization import Organization
from user.models.user import UserExt

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def user(db) -> UserExt:
    return baker.make(UserExt)


@pytest.fixture
def other_user(db) -> UserExt:
    return baker.make(UserExt)


@pytest.fixture
def authed_client(user: UserExt) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client() -> APIClient:
    return APIClient()


@pytest.fixture
def organization(db) -> Organization:
    return baker.make(Organization)


@pytest.fixture
def event(organization: Organization) -> Event:
    return Event.objects.create(
        organization=organization,
        name="파이콘 한국 2026",
        event_start_at=datetime(2026, 8, 15),
    )


@pytest.fixture
def other_event(organization: Organization) -> Event:
    return Event.objects.create(
        organization=organization,
        name="파이콘 한국 2025",
        event_start_at=datetime(2025, 8, 15),
    )


@pytest.fixture
def presentation_type(event: Event) -> PresentationType:
    return PresentationType.objects.create(event=event, name="Talk")


@pytest.fixture
def presentation(presentation_type: PresentationType) -> Presentation:
    return Presentation.objects.create(type=presentation_type, title="Django 심화")


@pytest.fixture
def presentation_2(presentation_type: PresentationType) -> Presentation:
    return Presentation.objects.create(type=presentation_type, title="FastAPI 입문")


@pytest.fixture
def other_event_presentation(other_event: Event) -> Presentation:
    pt = PresentationType.objects.create(event=other_event, name="Talk")
    return Presentation.objects.create(type=pt, title="작년 발표")


# ──────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────


def list_url(event_id: uuid.UUID | str) -> str:
    return reverse("v1:presentation-bookmark-list", kwargs={"event_id": str(event_id)})


def detail_url(event_id: uuid.UUID | str, presentation_id: uuid.UUID | str) -> str:
    return reverse(
        "v1:presentation-bookmark-detail",
        kwargs={"event_id": str(event_id), "presentation_id": str(presentation_id)},
    )


# ══════════════════════════════════════════════
# GET /v1/events/{event_id}/presentation-bookmarks/
# ══════════════════════════════════════════════


class TestBookmarkList:
    """GET 북마크 목록 조회 API 테스트"""

    @pytest.mark.django_db
    def test_returns_empty_list_when_no_bookmarks(self, authed_client: APIClient, event: Event):
        """
        북마크가 하나도 없을 때 빈 배열을 반환하는지 검증합니다.
        프론트에서 빈 상태 UI를 렌더링하기 위해 빈 배열이 정상 응답이어야 합니다.
        """
        response = authed_client.get(list_url(event.id))

        assert response.status_code == http.HTTPStatus.OK
        assert response.json()["presentation_ids"] == []

    @pytest.mark.django_db
    def test_returns_bookmarked_presentation_ids(
        self,
        authed_client: APIClient,
        user: UserExt,
        event: Event,
        presentation: Presentation,
        presentation_2: Presentation,
    ):
        """
        유저가 북마크한 세션의 presentation_id 목록이 정확히 반환되는지 검증합니다.
        프론트는 이 ID 목록을 전체 세션 목록과 매칭해서 내 시간표를 구성합니다.
        """
        PresentationBookmark.objects.create(user=user, presentation=presentation)
        PresentationBookmark.objects.create(user=user, presentation=presentation_2)

        response = authed_client.get(list_url(event.id))

        assert response.status_code == http.HTTPStatus.OK
        returned_ids = set(response.json()["presentation_ids"])
        assert returned_ids == {str(presentation.id), str(presentation_2.id)}

    @pytest.mark.django_db
    def test_filters_by_event_id(
        self,
        authed_client: APIClient,
        user: UserExt,
        event: Event,
        other_event: Event,
        presentation: Presentation,
        other_event_presentation: Presentation,
    ):
        """
        event_id path로 필터링했을 때, 해당 행사의 북마크만 반환되는지 검증합니다.
        다른 행사의 북마크가 섞여 나오면 안 됩니다.
        """
        PresentationBookmark.objects.create(user=user, presentation=presentation)
        PresentationBookmark.objects.create(user=user, presentation=other_event_presentation)

        response = authed_client.get(list_url(event.id))

        assert response.status_code == http.HTTPStatus.OK
        returned_ids = response.json()["presentation_ids"]
        assert len(returned_ids) == 1
        assert returned_ids[0] == str(presentation.id)

    @pytest.mark.django_db
    def test_does_not_return_other_users_bookmarks(
        self, authed_client: APIClient, other_user: UserExt, event: Event, presentation: Presentation
    ):
        """
        다른 유저가 북마크한 세션이 현재 유저의 목록에 포함되지 않는지 검증합니다.
        북마크는 유저별로 완전히 격리되어야 합니다.
        """
        PresentationBookmark.objects.create(user=other_user, presentation=presentation)

        response = authed_client.get(list_url(event.id))

        assert response.status_code == http.HTTPStatus.OK
        assert response.json()["presentation_ids"] == []

    @pytest.mark.django_db
    def test_unauthenticated_returns_403(self, anon_client: APIClient, event: Event):
        """
        로그인하지 않은 유저가 요청하면 403 Forbidden을 반환하는지 검증합니다.
        DRF SessionAuthentication은 쿠키 없는 요청을 AnonymousUser로 통과시키고,
        IsAuthenticated 권한 체크에서 403을 반환합니다.
        프론트는 403을 받으면 로그인 모달을 띄웁니다.
        """
        response = anon_client.get(list_url(event.id))

        assert response.status_code == http.HTTPStatus.FORBIDDEN

    @pytest.mark.django_db
    def test_nonexistent_event_returns_404(self, authed_client: APIClient):
        """
        존재하지 않는 event_id로 요청하면 404를 반환하는지 검증합니다.
        """
        response = authed_client.get(list_url(uuid.uuid4()))

        assert response.status_code == http.HTTPStatus.NOT_FOUND


# ══════════════════════════════════════════════
# POST /v1/events/{event_id}/presentation-bookmarks/
# ══════════════════════════════════════════════


class TestBookmarkCreate:
    """POST 북마크 추가 API 테스트"""

    @pytest.mark.django_db
    def test_creates_bookmark_and_returns_201(
        self, authed_client: APIClient, user: UserExt, event: Event, presentation: Presentation
    ):
        """
        새로운 세션을 북마크하면 201 Created와 함께
        해당 presentation_id가 응답으로 반환되는지 검증합니다.
        DB에 북마크 레코드가 실제로 생성되었는지도 확인합니다.
        """
        response = authed_client.post(
            list_url(event.id),
            data={"presentation_id": str(presentation.id)},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.CREATED
        assert response.json()["presentation_id"] == str(presentation.id)
        assert PresentationBookmark.objects.filter(user=user, presentation=presentation).exists()

    @pytest.mark.django_db
    def test_sets_event_from_presentation(
        self, authed_client: APIClient, user: UserExt, event: Event, presentation: Presentation
    ):
        """
        북마크 생성 시 presentation의 type.event로부터 event를 자동 설정하는지 검증합니다.
        프론트는 POST 시 event를 명시적으로 보내지 않으므로, 서버가 presentation에서 파생해야 합니다.
        """
        authed_client.post(list_url(event.id), data={"presentation_id": str(presentation.id)}, format="json")

        bookmark = PresentationBookmark.objects.get(user=user, presentation=presentation)
        assert bookmark.presentation.type.event.id == event.id

    @pytest.mark.django_db
    def test_duplicate_bookmark_returns_200_idempotent(
        self, authed_client: APIClient, user: UserExt, event: Event, presentation: Presentation
    ):
        """
        이미 북마크한 세션을 다시 추가하면 에러 대신 200 OK를 반환하는지 검증합니다.
        (멱등성) 프론트의 되돌리기/연타로 중복 요청이 발생할 수 있으므로,
        두 번째 요청도 정상 응답이어야 합니다.
        """
        PresentationBookmark.objects.create(user=user, presentation=presentation)

        response = authed_client.post(
            list_url(event.id),
            data={"presentation_id": str(presentation.id)},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.OK
        assert response.json()["presentation_id"] == str(presentation.id)
        # 중복 레코드가 생성되지 않았는지 확인
        assert PresentationBookmark.objects.filter(user=user, presentation=presentation).count() == 1

    @pytest.mark.django_db
    def test_nonexistent_presentation_returns_404(self, authed_client: APIClient, event: Event):
        """
        존재하지 않는 presentation_id로 북마크를 추가하면 404를 반환하는지 검증합니다.
        """
        response = authed_client.post(
            list_url(event.id),
            data={"presentation_id": str(uuid.uuid4())},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.NOT_FOUND

    @pytest.mark.django_db
    def test_soft_deleted_presentation_returns_404(
        self, authed_client: APIClient, event: Event, presentation: Presentation
    ):
        """
        소프트 삭제된(deleted_at이 설정된) presentation을 북마크하려고 하면
        404를 반환하는지 검증합니다.
        filter_active()가 삭제된 레코드를 제외해야 합니다.
        """
        presentation.delete()

        response = authed_client.post(
            list_url(event.id),
            data={"presentation_id": str(presentation.id)},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.NOT_FOUND

    @pytest.mark.django_db
    def test_invalid_presentation_id_format_returns_400(self, authed_client: APIClient, event: Event):
        """
        presentation_id에 UUID가 아닌 값을 보내면 400 Bad Request를 반환하는지 검증합니다.
        serializer의 UUIDField 유효성 검사가 동작해야 합니다.
        """
        response = authed_client.post(
            list_url(event.id),
            data={"presentation_id": "not-a-uuid"},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.BAD_REQUEST

    @pytest.mark.django_db
    def test_missing_presentation_id_returns_400(self, authed_client: APIClient, event: Event):
        """
        요청 바디에 presentation 필드가 없으면 400 Bad Request를 반환하는지 검증합니다.
        """
        response = authed_client.post(list_url(event.id), data={}, format="json")

        assert response.status_code == http.HTTPStatus.BAD_REQUEST

    @pytest.mark.django_db
    def test_unauthenticated_returns_403(self, anon_client: APIClient, event: Event, presentation: Presentation):
        """
        로그인하지 않은 유저가 북마크 추가를 시도하면 403 Forbidden을 반환하는지 검증합니다.
        DRF SessionAuthentication은 쿠키 없는 요청을 AnonymousUser로 통과시키고,
        IsAuthenticated 권한 체크에서 403을 반환합니다.
        """
        response = anon_client.post(
            list_url(event.id),
            data={"presentation_id": str(presentation.id)},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.FORBIDDEN

    @pytest.mark.django_db
    def test_allows_overlapping_time_sessions(
        self,
        authed_client: APIClient,
        user: UserExt,
        event: Event,
        presentation: Presentation,
        presentation_2: Presentation,
    ):
        """
        시간이 겹치는 세션들도 모두 북마크할 수 있는지 검증합니다.
        UX 확정 사항: 겹침 경고는 프론트가 처리하고, 서버는 시간대 충돌을 검사하지 않습니다.
        """
        resp1 = authed_client.post(list_url(event.id), data={"presentation_id": str(presentation.id)}, format="json")
        resp2 = authed_client.post(list_url(event.id), data={"presentation_id": str(presentation_2.id)}, format="json")

        assert resp1.status_code == http.HTTPStatus.CREATED
        assert resp2.status_code == http.HTTPStatus.CREATED
        assert PresentationBookmark.objects.filter(user=user).count() == 2

    @pytest.mark.django_db
    def test_nonexistent_event_returns_404(self, authed_client: APIClient, presentation: Presentation):
        """
        존재하지 않는 event_id로 북마크를 추가하면 404를 반환하는지 검증합니다.
        """
        response = authed_client.post(
            list_url(uuid.uuid4()),
            data={"presentation_id": str(presentation.id)},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.NOT_FOUND


# ══════════════════════════════════════════════
# DELETE /v1/events/{event_id}/presentation-bookmarks/{presentation_id}/
# ══════════════════════════════════════════════


class TestBookmarkDestroy:
    """DELETE 북마크 삭제 API 테스트"""

    @pytest.mark.django_db
    def test_deletes_bookmark_and_returns_204(
        self, authed_client: APIClient, user: UserExt, event: Event, presentation: Presentation
    ):
        """
        북마크된 세션을 삭제하면 204 No Content를 반환하고,
        DB에서 실제로 레코드가 삭제(hard delete)되는지 검증합니다.
        """
        PresentationBookmark.objects.create(user=user, presentation=presentation)

        response = authed_client.delete(detail_url(event.id, presentation.id))

        assert response.status_code == http.HTTPStatus.NO_CONTENT
        assert not PresentationBookmark.objects.filter(user=user, presentation=presentation).exists()

    @pytest.mark.django_db
    def test_not_bookmarked_returns_204_idempotent(
        self, authed_client: APIClient, event: Event, presentation: Presentation
    ):
        """
        유저가 북마크하지 않은 세션에 대해 삭제를 요청해도
        에러 대신 204를 반환하는지 검증합니다. (멱등성)
        프론트의 되돌리기 UX에서 DELETE 직후 같은 세션에 POST가 오고,
        다시 DELETE가 올 수 있으므로 멱등이어야 합니다.
        """
        response = authed_client.delete(detail_url(event.id, presentation.id))

        assert response.status_code == http.HTTPStatus.NO_CONTENT

    @pytest.mark.django_db
    def test_nonexistent_presentation_returns_404(self, authed_client: APIClient, event: Event):
        """
        존재하지 않는 presentation_id로 삭제를 요청하면 404를 반환하는지 검증합니다.
        presentation 자체가 DB에 없는 경우만 404이고,
        presentation은 있지만 북마크가 없는 경우는 204입니다.
        """
        response = authed_client.delete(detail_url(event.id, uuid.uuid4()))

        assert response.status_code == http.HTTPStatus.NOT_FOUND

    @pytest.mark.django_db
    def test_does_not_delete_other_users_bookmark(
        self, authed_client: APIClient, other_user: UserExt, event: Event, presentation: Presentation
    ):
        """
        삭제 요청이 다른 유저의 북마크에 영향을 주지 않는지 검증합니다.
        user.presentation 필터로 현재 유저의 북마크만 삭제해야 합니다.
        """
        PresentationBookmark.objects.create(user=other_user, presentation=presentation)

        response = authed_client.delete(detail_url(event.id, presentation.id))

        assert response.status_code == http.HTTPStatus.NO_CONTENT
        # 다른 유저의 북마크는 그대로 남아 있어야 함
        assert PresentationBookmark.objects.filter(user=other_user, presentation=presentation).exists()

    @pytest.mark.django_db
    def test_unauthenticated_returns_403(self, anon_client: APIClient, event: Event, presentation: Presentation):
        """
        로그인하지 않은 유저가 북마크 삭제를 시도하면 403 Forbidden을 반환하는지 검증합니다.
        DRF SessionAuthentication은 쿠키 없는 요청을 AnonymousUser로 통과시키고,
        IsAuthenticated 권한 체크에서 403을 반환합니다.
        """
        response = anon_client.delete(detail_url(event.id, presentation.id))

        assert response.status_code == http.HTTPStatus.FORBIDDEN

    @pytest.mark.django_db
    def test_only_deletes_specified_bookmark(
        self,
        authed_client: APIClient,
        user: UserExt,
        event: Event,
        presentation: Presentation,
        presentation_2: Presentation,
    ):
        """
        특정 세션 하나를 삭제할 때, 유저의 다른 북마크는 유지되는지 검증합니다.
        삭제 범위가 정확히 요청된 presentation에만 한정되어야 합니다.
        """
        PresentationBookmark.objects.create(user=user, presentation=presentation)
        PresentationBookmark.objects.create(user=user, presentation=presentation_2)

        authed_client.delete(detail_url(event.id, presentation.id))

        assert not PresentationBookmark.objects.filter(user=user, presentation=presentation).exists()
        assert PresentationBookmark.objects.filter(user=user, presentation=presentation_2).exists()

    @pytest.mark.django_db
    def test_nonexistent_event_returns_404(self, authed_client: APIClient, presentation: Presentation):
        """
        존재하지 않는 event_id로 삭제를 요청하면 404를 반환하는지 검증합니다.
        """
        response = authed_client.delete(detail_url(uuid.uuid4(), presentation.id))

        assert response.status_code == http.HTTPStatus.NOT_FOUND


# ══════════════════════════════════════════════
# 통합 시나리오: 담기 → 빼기 → 되돌리기 (POST → DELETE → POST)
# ══════════════════════════════════════════════


class TestBookmarkUndoFlow:
    """프론트의 '담기 → 빼기 → 되돌리기' 시나리오 통합 테스트"""

    @pytest.mark.django_db
    def test_add_remove_re_add_flow(
        self, authed_client: APIClient, user: UserExt, event: Event, presentation: Presentation
    ):
        """
        프론트의 실제 사용 시나리오를 재현합니다:
        1. 세션 담기 (POST) → 201
        2. 세션 빼기 (DELETE) → 204
        3. 되돌리기 (POST 재전송) → 201
        각 단계에서 GET으로 목록을 조회해 상태가 올바른지 확인합니다.
        """
        # 1단계: 담기
        resp = authed_client.post(list_url(event.id), data={"presentation_id": str(presentation.id)}, format="json")
        assert resp.status_code == http.HTTPStatus.CREATED

        # GET으로 확인: 1개
        resp = authed_client.get(list_url(event.id))
        assert len(resp.json()["presentation_ids"]) == 1

        # 2단계: 빼기
        resp = authed_client.delete(detail_url(event.id, presentation.id))
        assert resp.status_code == http.HTTPStatus.NO_CONTENT

        # GET으로 확인: 0개
        resp = authed_client.get(list_url(event.id))
        assert len(resp.json()["presentation_ids"]) == 0

        # 3단계: 되돌리기 (다시 POST)
        resp = authed_client.post(list_url(event.id), data={"presentation_id": str(presentation.id)}, format="json")
        assert resp.status_code == http.HTTPStatus.CREATED

        # GET으로 확인: 다시 1개
        resp = authed_client.get(list_url(event.id))
        assert len(resp.json()["presentation_ids"]) == 1

    @pytest.mark.django_db
    def test_rapid_double_delete_is_safe(
        self, authed_client: APIClient, user: UserExt, event: Event, presentation: Presentation
    ):
        """
        같은 세션에 대해 DELETE가 빠르게 2번 연속 호출되어도
        두 번째 요청이 에러 없이 204를 반환하는지 검증합니다.
        네트워크 재시도나 프론트 연타로 발생할 수 있는 시나리오입니다.
        """
        PresentationBookmark.objects.create(user=user, presentation=presentation)

        resp1 = authed_client.delete(detail_url(event.id, presentation.id))
        resp2 = authed_client.delete(detail_url(event.id, presentation.id))

        assert resp1.status_code == http.HTTPStatus.NO_CONTENT
        assert resp2.status_code == http.HTTPStatus.NO_CONTENT

    @pytest.mark.django_db
    def test_rapid_double_post_is_safe(
        self, authed_client: APIClient, user: UserExt, event: Event, presentation: Presentation
    ):
        """
        같은 세션에 대해 POST가 빠르게 2번 연속 호출되어도
        두 번째 요청이 에러 없이 200을 반환하고 중복 레코드가 생기지 않는지 검증합니다.
        """
        resp1 = authed_client.post(list_url(event.id), data={"presentation_id": str(presentation.id)}, format="json")
        resp2 = authed_client.post(list_url(event.id), data={"presentation_id": str(presentation.id)}, format="json")

        assert resp1.status_code == http.HTTPStatus.CREATED
        assert resp2.status_code == http.HTTPStatus.OK
        assert PresentationBookmark.objects.filter(user=user, presentation=presentation).count() == 1


# ══════════════════════════════════════════════
# 에러 응답 포맷 검증
# ══════════════════════════════════════════════


class TestErrorResponseFormat:
    """에러 응답이 drf-standardized-errors의 공통 envelope 포맷을 따르는지 검증"""

    @pytest.mark.django_db
    def test_403_follows_error_envelope(self, anon_client: APIClient, event: Event):
        """
        403 응답이 프론트의 ErrorResponseSchema와 호환되는
        { "type": "...", "errors": [{ "code": "...", "detail": "...", "attr": ... }] }
        포맷인지 검증합니다.
        프론트는 errors[0].code로 에러 종류를 분기합니다.
        DRF SessionAuthentication + IsAuthenticated 조합에서
        미인증 요청은 403 + code: "not_authenticated"로 응답합니다.
        """
        response = anon_client.get(list_url(event.id))

        assert response.status_code == http.HTTPStatus.FORBIDDEN
        body = response.json()
        assert "type" in body
        assert "errors" in body
        assert len(body["errors"]) > 0
        assert "code" in body["errors"][0]
        assert "detail" in body["errors"][0]
        assert body["errors"][0]["code"] == "not_authenticated"

    @pytest.mark.django_db
    def test_404_follows_error_envelope(self, authed_client: APIClient, event: Event):
        """
        404 응답이 공통 에러 envelope 포맷을 따르는지 검증합니다.
        """
        response = authed_client.post(
            list_url(event.id),
            data={"presentation_id": str(uuid.uuid4())},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.NOT_FOUND
        body = response.json()
        assert body["type"] == "client_error"
        assert "errors" in body
        assert body["errors"][0]["code"] == "not_found"

    @pytest.mark.django_db
    def test_400_validation_error_follows_envelope(self, authed_client: APIClient, event: Event):
        """
        400 유효성 검사 에러가 공통 에러 envelope 포맷을 따르는지 검증합니다.
        """
        response = authed_client.post(
            list_url(event.id),
            data={"presentation_id": "invalid"},
            format="json",
        )

        assert response.status_code == http.HTTPStatus.BAD_REQUEST
        body = response.json()
        assert body["type"] == "validation_error"
        assert "errors" in body
