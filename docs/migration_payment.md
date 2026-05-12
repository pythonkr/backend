# `python-korea-payment` → `backend` 통합 plan

## 1. 개요

`/Users/musoftware/workspace_pycon/python-korea-payment`(이하 `payment`)을 본
`backend` 저장소의 sub-app으로 흡수한다. 양쪽 모두 같은 손이 만든 Django 5/6
프로젝트라 호환성은 매우 높고, 데이터는 **동일 host의 다른 database**로 분리되어
있으며 현재 `payment`에는 신규 데이터가 들어가지 않는 상태다.

## 2. 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| 흡수 위치 | `app/shop/`(부모는 빈 패키지) 하위로 `order`, `product`, `payment_history` sub-app |
| `purchase_shared` 처리 | 별도 앱으로 두지 않고 `core`(인프라)와 `shop`(도메인)로 분해 흡수 |
| `BaseAbstractModel` | `core.models.BaseAbstractModel` 단일 사용. payment 코드는 import 교체만 |
| Django admin | 드롭. `admin_api` viewset으로 재구현 |
| 데이터 이관 | 동일 host 내 `pg_dump`/`psql` 작업 (database 분리이므로 cross-DB INSERT 불가) |
| 마이그레이션 | 신규 마이그레이션을 작성하고 cutover 시 `migrate --fake`로 history 정합 |
| `historical_*` | 통째 TRUNCATE 후 새로 시작 |
| User 모델 | backend `user.UserExt`로 병합 (payment 측 데이터를 흡수). `unique_id` 필드 추가 필요 |
| Allauth | 도입. 양쪽 쿠키/세션 정책은 backend 기준으로 통일 |
| Celery/Redis | 이미 이관 완료. 별도 작업 없음 |
| `shop_*` 테이블 prefix | **불필요** — `shop.order` AppConfig은 `app_label="order"`로 자동 생성되어 db_table은 `order_*` 그대로 유지 (event.presentation 패턴과 동일) |

## 3. 최종 구조

```
app/
├── core/
│   ├── external_apis/
│   │   ├── slack/                 # 기존
│   │   ├── nhn_cloud_*.py         # 기존
│   │   ├── smtp_email.py          # 기존
│   │   └── portone/               # ← purchase_shared/external_apis/portone
│   ├── permissions/
│   │   └── api_key.py             # ← purchase_shared/auth/api_key.py
│   ├── const/
│   │   ├── regex.py               # 기존 + ALLOW_ALL/EMAIL/PHONE 추가 (← purchase_shared/consts/regex.py)
│   │   ├── tag.py                 # 기존 + SHOP_*/EXT_* OpenAPITag 추가 (← purchase_shared/consts/tag.py)
│   │   └── shop_error_messages.py # ← purchase_shared/consts/error_messages.py (이름 명확화)
│   ├── serializer/
│   │   └── nested_model_serializer.py # ← purchase_shared/serializers/common.py (InstanceListSerializer, NestedModelSerializer)
│   ├── util/
│   │   ├── strutil.py             # ← purchase_shared/utils/str_utils.py (uuid_to_b64, b64_to_uuid). UUID regex 는 core/const/regex 재사용
│   │   ├── totp.py                # ← purchase_shared/utils/totp.py
│   │   ├── grouper.py             # ← purchase_shared/utils/django.py (grouper, query_grouper)
│   │   └── thread_local.py        # 기존
│   └── models.py                  # 기존 (BaseAbstractModel 단일 출처)
├── shop/
│   ├── __init__.py                # 빈 패키지
│   ├── serializers/
│   │   ├── cart_validation.py     # ← purchase_shared/serializers/cart_validation.py
│   │   └── refund.py
│   ├── order/
│   │   ├── apps.py                # name="shop.order"
│   │   ├── models.py
│   │   ├── views/, serializers/, urls.py, translation.py
│   ├── product/
│   │   ├── apps.py                # name="shop.product"
│   │   └── ...
│   ├── payment_history/
│   │   ├── apps.py                # name="shop.payment_history"
│   │   └── ...                    # PortOne webhook viewset 포함
│   └── external_api/              # 외부에서 호출되는 API (sub-app 아닌 모듈 묶음)
│       ├── filters.py             # desk_support, patron filterset
│       ├── serializers.py         # desk_support, patron serializer
│       ├── views.py               # DeskSupportExternalAPIViewSet, PatronExternalAPIViewSet
│       └── urls.py                # v1/external-api/{desk-support,patron}/ 로 노출
├── admin_api/
│   ├── views/
│   │   ├── shop_orders.py         # 신규 (admin.py 의 actions를 viewset으로)
│   │   ├── shop_products.py
│   │   ├── shop_payment_histories.py
│   │   └── shop_refund_authorizer.py  # TOTP
│   ├── serializers/, urls.py, ...
└── user/                          # 기존 + payment 측 user 흡수
    └── models/
        └── user.py                # UserExt 에 unique_id 필드 추가 + scancode 메서드 이식
```

## 4. `purchase_shared` 분해 매핑

| from | to | 비고 |
|---|---|---|
| `purchase_shared/models.py` | **폐기** | `core.models` 사용 |
| `purchase_shared/auth/api_key.py` | `core/permissions/api_key.py` | |
| `purchase_shared/consts/error_messages.py` | `core/const/shop_error_messages.py` | 파일명에 `shop_` 명시. PR A 의 `INVALID_API_KEY_MESSAGE` inline 정의도 그대로 유지 |
| `purchase_shared/consts/regex.py` | `core/const/regex.py` 에 병합 | `ALLOW_ALL`, `EMAIL`, `PHONE` 추가 |
| `purchase_shared/consts/tag.py` | `core/const/tag.py` 에 병합 | `OpenAPITag.SHOP_*` (USER/PRODUCT/CART/ORDER/ORDER_REFUND/PORTONE_WEBHOOK), `EXT_REGISTRATION_DESK_API`, `EXT_PATRON_API` 추가 |
| `purchase_shared/external_apis/portone/` | `core/external_apis/portone/` | |
| `purchase_shared/external_apis/slack/` | **폐기** | backend에 동일 모듈 존재 |
| `purchase_shared/middleware/request_response_logger.py` | **폐기** | backend에 존재 |
| `purchase_shared/logger/` | **폐기** | backend에 존재 |
| `purchase_shared/utils/django.py` | `core/util/grouper.py` | `grouper`, `query_grouper` 함수 둘 다 |
| `purchase_shared/utils/openapi.py` | `core/openapi/` 합치기 | backend 동명 모듈 충돌 확인 |
| `purchase_shared/utils/str_utils.py` | `core/util/strutil.py` | `UUID_PATTERN`/`UUID_REGEX` 정의는 `core/const/regex.py` 의 `UUID_V4_*` 로 통합 (사용처는 `from core.const.regex import UUID_V4_REGEX`). 파일명은 backend `dateutil.py` 컨벤션 따름 |
| `purchase_shared/utils/totp.py` | `core/util/totp.py` | |
| `purchase_shared/serializers/common.py` | `core/serializer/nested_model_serializer.py` | `InstanceListSerializer`, `NestedModelSerializer` (도메인 무관) |
| `purchase_shared/serializers/{cart_validation,refund}.py` | `shop/serializers/*` | shop 도메인 로직 |
| `purchase_shared/serializers/notification.py` | **폐기** | NotiCo SQS 직접 호출 흐름 폐기 예정. PR C 에서 backend `notification` 앱 (Celery + 템플릿 시스템) 활용해 재구현 |
| `purchase_shared/admin_views/`, `admin_urls.py`, `templates/` | **폐기** | admin_api로 재구현 |
| `purchase_shared/apps.py` | **폐기** | `purchase_shared` 자체 사라짐 |

## 5. UserExt 비교 결과 및 병합 전략

### 5.1 코드 차원 차이

| 항목 | backend | payment |
|---|---|---|
| 상속 | `AbstractUser` | `AbstractUser` |
| PK | `id` (BigAuto) | `id` (BigAuto) |
| 추가 필드 | `image` (FK→`file.PublicFile`), `nickname` | `unique_id` (UUIDField, unique) |
| 인덱스 | — | `userext_unique_id_idx` |
| simple-history | 적용 | 미적용 |
| 도메인 메서드 | `get_system_user()` | `scancode_*`, `purchased_orders`, `purchased_orders_in_last_six_months` |

### 5.2 병합 후 모델 (PR D에서 작업)

backend `user.UserExt`에 다음 추가:
- `unique_id = models.UUIDField(unique=True, editable=False, default=uuid4)`
- 인덱스 `userext_unique_id_idx`
- payment의 scancode 메서드 4개 + `purchased_orders` 2개 이식
- 기존 backend user 행은 마이그레이션 시 `default=uuid4`로 자동 채움

### 5.3 검증 결과 (확정)

PR D 작업 전 양쪽 DB에서 사전 검증한 결과:

**양쪽 user 통계**

| | payment (`pyconkr_purchase_prod_db`) | backend (`pyconkr_2025_prod_db`) |
|---|---|---|
| total | 2,299 | 72 |
| min_id ~ max_id | 1 ~ 2,299 | 0 ~ 75 |
| empty_email | 0 | 0 |
| duplicate_email | 4 | 0 |

**backend `id=0` = SYSTEM_USER** (`system@python.or.kr`, super). 침범 금지.

**email 매칭 (도메인 정규화 `@pycon.kr` → `@python.or.kr` 적용)**

| | 값 |
|---|---|
| 자동 매칭 distinct email | 42 |
| 자동 매칭 payment row | 45 |
| 1:N 매칭 케이스 | 3 (`cpprhtn`, `emscb`, `ppiyakk2`) |

**도메인 분포 (payment)**: `@pycon.kr` 12 / `@python.or.kr` 16 / `@gmail.com` 1,170

**확정 정책**:
- `@pycon.kr` ↔ `@python.or.kr` 동일인 (내부 운영자) → 자동 매칭 시 정규화로 처리
- 그 외 도메인(`@gmail.com` 등) → 자동 매칭 안 함. 동일인은 매뉴얼 매핑 테이블에 명시
- 매뉴얼 매핑 1건 확정: `darjeeling@gmail.com` (payment id 5, 1135) → backend `darjeeling@python.or.kr`

### 5.4 cutover 시 user 병합 절차

오프셋: `OFFSET = MAX(backend.id) + 100 = 175`. payment.id 1~2,299 → 새 id 176~2,474. backend 0~75과 충돌 없음.

```sql
-- payment DB에서 실행 (dump 직전)
-- 매핑 테이블 생성

CREATE TABLE _user_id_mapping (
    payment_id INT PRIMARY KEY,
    backend_id INT NOT NULL,
    source     TEXT NOT NULL  -- 'auto' | 'manual' | 'shifted'
);

-- (1) 자동 매칭: 정규화 후 email JOIN
--     backend (email, id) 페어 72개는 Appendix A 참조
INSERT INTO _user_id_mapping (payment_id, backend_id, source)
SELECT u.id, be.backend_id, 'auto'
FROM user_userext u
JOIN (VALUES
    -- ⬇ Appendix A 의 72개 페어를 그대로 붙여넣음
    ('system@python.or.kr', 0),
    ('musoftware@python.or.kr', 1),
    -- ...
    ('session@email.com', 75)
) AS be(email, backend_id)
  ON LOWER(REGEXP_REPLACE(u.email, '@pycon\.kr$', '@python.or.kr')) = LOWER(be.email);

-- (2) 매뉴얼 매핑 (darjeeling@gmail.com → backend darjeeling@python.or.kr id=5)
INSERT INTO _user_id_mapping (payment_id, backend_id, source)
VALUES
    (5,    5, 'manual'),
    (1135, 5, 'manual');

-- (3) 매핑 안 된 나머지 → PK 시프트
INSERT INTO _user_id_mapping (payment_id, backend_id, source)
SELECT p.id, p.id + 175, 'shifted'
FROM user_userext p
WHERE p.id NOT IN (SELECT payment_id FROM _user_id_mapping);

-- (4) 정합성 검증
SELECT source, COUNT(*) FROM _user_id_mapping GROUP BY source;
-- 기대: auto=45, manual=2, shifted=2252, 합계=2299
```

**dump 변환 흐름**:
1. `_user_id_mapping` 을 활용해 payment dump의 다음 컬럼을 모두 갱신
   - `user_userext.id`, `auth_user_groups.user_id`, `auth_user_user_permissions.user_id`
   - 모든 shop 테이블의 `user_id`, `created_by_id`, `updated_by_id`, `deleted_by_id`
2. `source IN ('auto', 'manual')` 인 payment user는 새 user INSERT 안 함 (이미 backend에 있음)
3. `source = 'shifted'` 인 payment user (2,252건)만 backend `user_userext` 에 INSERT
4. backend `user_userext.image_id`, `user_userext.nickname` 컬럼은 NULL로 채움 (payment 측에 없는 컬럼)
5. `user_userext.unique_id` 는 payment 측 값 그대로 (PR D에서 추가된 신규 컬럼이지만 payment 측에도 동일 컬럼 존재)

## 6. 단계별 작업 (PR 5개)

각 PR은 단독 머지 가능해야 하며 머지 후에도 기존 backend 기능은 그대로 동작해야
한다. cutover 직전까지 `shop`은 비활성 상태로 둔다.

### PR A — 의존성·settings + `core` 인프라 흡수

**범위**
- `pyproject.toml`: `django-allauth[openid,socialaccount]`, `shortuuid`, `cryptography`, 기타 누락분 추가
- `core/settings.py`: `PORTONE_*`, `NHN_KCP_*`, `ORDER_SCANCODE_SALT`, `REFUND_AUTHORIZER_SECRET_KEY`, `EXT_API_KEYS`, `SHOP_DOMAIN`, allauth 관련 설정 추가 (단 `INSTALLED_APPS`에 allauth 등록은 PR D에서)
- `envfile/.env.local` 샘플 갱신
- `core/external_apis/portone/` 추가
- `core/permissions/api_key.py` 추가
- `core/util/str_utils.py`, `core/util/totp.py`, `core/util/query_grouper.py` 추가
- `core/openapi/` 의 기존 모듈과 payment `utils/openapi.py` 충돌 확인 후 병합

**검증**
- `python manage.py check` 통과
- 기존 backend 테스트 회귀 통과
- shell에서 `from core.external_apis.portone.client import portone_client` 등 import 동작 확인

### PR B — `shop` sub-app + URL/view + 템플릿

**범위**
- `app/shop/__init__.py` (빈 패키지)
- `shop/const/`, `shop/serializers/` 추가
- `shop/order/`, `shop/product/`, `shop/payment_history/` 디렉토리에 payment 코드 이식
  - 모든 모델의 `BaseAbstractModel` import를 `core.models`로 교체
  - `purchase_shared.*` import 전부 새 위치로 갱신
  - `SingleProductCart.to_order()` 의 `self.delete()` → `SingleProductCart.objects.filter(id=self.id).hard_delete()` 로 의도적 hard delete 명시화
  - **settings 참조 갱신** (PR A 에서 namespace 화 됨):
    - `settings.SHOP_API_DOMAIN` / `settings.SHOP_DOMAIN` → `settings.BACKEND_DOMAIN`
      (사용처 4건: `order/serializers/dto.py` 2회, `purchase_shared/serializers/notification.py`, `user/serializers.py`)
    - `settings.PORTONE_API_URL` / `PORTONE_IMP_KEY` / `PORTONE_IMP_SECRET` / `PORTONE_IP_LIST` → `settings.PORTONE.{api_url,imp_key,imp_secret,ip_list}`
    - `settings.NHN_KCP_PG_API_CERT` / `PRIVATE_KEY` / `PASSWORD` → `settings.NHN_KCP.{pg_api_cert,pg_api_private_key,pg_api_password}`
      (PR A 에서 PEM header/footer 자동 wrapping 제거됨 → 환경변수에 PEM 형식 그대로 넣어야 함)
    - `settings.ORDER_SCANCODE_SALT` → `settings.SHOP.order_scancode_salt`
    - `settings.REFUND_AUTHORIZER_SECRET_KEY` → `settings.SHOP.refund_authorizer_secret_key`
  - **import 경로 갱신** (PR A 통합 결과 반영):
    - `from purchase_shared.utils.str_utils import UUID_REGEX` → `from core.const.regex import UUID_V4_REGEX as UUID_REGEX` (또는 사용처에서 직접 `UUID_V4_REGEX` 사용)
    - `from purchase_shared.utils.openapi import build_html_responses` → `from core.openapi.schemas import build_html_responses`
- 각 sub-app `apps.py`: `name="shop.order"` 등
- `INSTALLED_APPS`에 `shop.order`, `shop.product`, `shop.payment_history` 추가
- 마이그레이션 신규 생성 (`makemigrations`)
- SYSTEM_USER 별도 seeding 불필요 — backend 운영 DB에 이미 존재 (id=0). dev/staging fresh DB 는 `core.util.thread_local.get_current_user()` 가 SYSTEM_USER 없으면 `None` 반환 (audit FK 가 null=True 라 OK), 또는 `UserExt.get_system_user()` 의 lazy `get_or_create` 패턴 활용
- `core/urls.py`의 `v1_apis`에 라우팅 추가 (별도 namespace 없이 v1 직속, 다른 sub-app 컨벤션과 일관):
  - `v1/shop/orders/`, `v1/shop/products/`, `v1/shop/payment-histories/`
  - reverse 경로는 `v1:<basename>` (예: `v1:orders-retrieve-scancode`)
- `shop/order/templates/` 의 사용자용 HTML 이식 (scancode_*.html, receipt_kcp.html — admin 템플릿은 제외)
- PortOne webhook 은 `payment_history/views.py` 에 정의되어 있으므로 `shop.payment_history` 로 자연스럽게 이전됨 (별도 작업 없음)
- `bad_response_slack_logger` import 경로: `purchase_shared.logger.util.decorator` → `core.logger.util.decorator` (backend 동일 정의 존재)
- **shop/external_api/ (`desk_support` + `patron`) 는 PR D 로 이동** — `UserExt.unique_id` 의존이 있어 UserExt 갱신과 함께 들어가야 함

**검증**
- `python manage.py makemigrations` 재실행 시 0개 변경
- `python manage.py migrate` 로컬 통과
- `python manage.py show_urls` 에서 `v1/shop/orders/`, `v1/shop/products/` 노출
- shell: `Order.objects.create(user=u, name="t")` 호출 시 `created_by`가 thread-local 의 인증 user / SYSTEM_USER (있으면) / `None` 으로 채워짐
- swagger UI에서 신규 endpoint 노출 확인

### PR C — `admin_api` shop endpoints

**범위**
- `admin_api/views/shop_orders.py`: list/retrieve/patch + refund + send_notification + bulk_send_notification + import_template + import + export
- `admin_api/views/shop_products.py`: Product/Category/CategoryGroup/Tag CRUD (+ OptionGroup/Option nested)
- `admin_api/views/shop_payment_histories.py`: read-only
- `admin_api/views/shop_refund_authorizer.py`: TOTP setup_qr + verify
- viewset에서 `shop/serializers/refund.py`, payment의 `imports.py`, `exports.py` 그대로 재사용
- TOTP 검증을 환불 endpoint 권한 클래스로 부착
- `admin_api/urls.py`에 라우팅 추가
- **알림 발송 (`send_notification`, `bulk_send_notification`)**: payment 의 `NotiCoMessageSerializer` (SQS) 흐름은 폐기. backend `notification` 앱 (Celery + 템플릿 시스템) 사용해 재구현. payment 의 `from_orders` 컨텍스트 빌드 로직은 참고만 하고 신규 작성

**검증**
- staging에서 골든패스 dry-run: 주문 조회 → 환불 → PaymentHistory 갱신 확인 (sandbox 키)
- CSV 가져오기/내보내기 1건 검증
- TOTP setup → verify → refund 흐름 1회 통과

### PR D — User 병합 + Allauth 통합 + UserExt 모델 갱신

**범위**
- `user.UserExt` 모델 갱신:
  - `unique_id` 필드 추가
  - 인덱스 추가
  - scancode 메서드 4개 (`scancode_token`, `scancode_path`, `from_short_unique_id`, `from_scancode_token`) 이식
  - `purchased_orders`, `purchased_orders_in_last_six_months` 이식
  - 기존 backend user 행에 `unique_id` 자동 채우는 마이그레이션
- `INSTALLED_APPS`에 `allauth`, `allauth.account`, `allauth.headless`, `allauth.socialaccount`, 12개 provider 추가
- `MIDDLEWARE`에 `allauth.account.middleware.AccountMiddleware` 추가
- `AUTHENTICATION_BACKENDS`에 allauth + `core.permissions.api_key.APIKeyAuthentication` 추가
- `ACCOUNT_*`, `SOCIALACCOUNT_*`, `HEADLESS_*` 설정 활성화
- 쿠키 정책 충돌 확인 (`COOKIE_PREFIX`, `SESSION_COOKIE_*`, CSRF는 backend 기준 유지)
- `accounts/`, `authn/social/` URL 추가
- `PASSWORD_HASHERS`에 Argon2 추가
- payment 측 social adapter (`NoNewUsersAccountAdapter`, `SocialAccountLoggingAdapter`) 이식
- `shop/external_api/` 추가 (PR B 에서 미뤄둔 `desk_support` + `patron`):
  - viewset, serializer, filterset 이식
  - `UserExt.unique_id` 사용처 활성화 (`SimpleUserDeskSupportDto.fields` 의 `unique_id`, `DeskSupportExternalAPIFilterSet.user_unique_id`)
  - `core/urls.py` 에 `v1/external-api/desk-support/`, `v1/external-api/patron/` 라우팅 추가

**검증**
- 로컬에서 Google OAuth 로그인 1회 통과
- 기존 backend Django 기본 login 회귀 동작 확인
- shell: 임의 user의 `scancode_token`/`purchased_orders` 동작 확인
- swagger UI 에서 `external-api/desk-support`, `external-api/patron` 노출 확인

**비고**: 데이터 차원의 user 병합은 cutover 단계에서 SQL로 진행

### PR E — 테스트 정비 + cutover 문서/SQL

**범위**
- payment 측에 있던 단위 테스트들 위치 이동 후 동작 확인
- 신규 admin_api endpoint 통합 테스트 작성 (최소 골든패스)
- PortOne mock fixture 정리
- `docs/cutover_payment.md` 작성: 아래 §7 절차를 그대로 옮김
- `infra/sql/cutover_payment.sql` 등 SQL 스니펫
- 운영 절차 (PortOne webhook URL 변경, allowlist 등) 체크리스트화

**검증**
- `pytest` 로컬 통과
- CI 통과
- §7.0 사전 dry-run 1회 성공 (모든 검증 통과 기준 충족, 실측값 기록 완료)

## 7. Cutover 절차 (database 분리 기준)

전제: PR A~E 머지 완료, **§7.0 dry-run 1회 이상 성공**.

### 7.0 사전 dry-run 검증 (production 적용 전 필수)

production payment/backend DB 를 손대기 전, 동일 절차를 격리 환경에서 1회 이상
완주하여 결과를 사전 검증한다.

**환경 준비**

| 항목 | 권장 |
|---|---|
| dry-run용 payment DB | production payment DB 의 **read-only 복제 또는 dump 복원본** |
| dry-run용 backend DB | production backend DB 의 **dump 복원본** (별도 인스턴스 / 별도 schema) |
| 실행 위치 | 로컬 또는 staging. **production 자격증명은 사용 금지** |
| PortOne | sandbox 키 사용 |

**수행할 단계**: 아래 §7.1 ~ §7.7 을 그대로 1회 완주.

**검증 통과 기준**

| 항목 | 기대값 / 확인 방법 |
|---|---|
| 매핑 테이블 분포 | `_user_id_mapping` source 별: `auto=45`, `manual=2`, `shifted=2252`, 합계 `2299` |
| 변환 후 user_userext INSERT 행 수 | 2,252 |
| 변환 후 shop 테이블 user FK 의 distinct 값 | 모두 backend `user_userext` 에 존재해야 함 |
| `python manage.py makemigrations` | 0 건 변경 (모델과 스키마가 일치) |
| `python manage.py check` | 통과 |
| `historical_*` 테이블 | 모두 0 row |
| 골든패스 1 — 주문 조회 | 임의 payment 주문이 새 admin_api 로 조회 가능 |
| 골든패스 2 — sandbox 환불 | 환불 1건 성공, `PaymentHistory` 신규 row 생성 |
| 골든패스 3 — scancode URL | reverse 결과가 `v1/shop/orders/...` 형식이고 200 응답 |
| 1:N 매핑 FK 정합성 | `cpprhtn`, `emscb`, `ppiyakk2` 의 payment 시절 주문이 backend 의 단일 user 로 모두 귀속됨 |

**기록**: dry-run 실행 결과 (각 검증 항목의 실측값) 를 PR E 또는 별도 issue 에 기록.
실패 항목이 있으면 plan/스크립트 보강 후 재실행.

**소요 시간**: 1회 완주 약 1~2시간 (dump 추출/적용이 대부분).

### 7.1 사전 점검

```sql
-- 양쪽 DB에서 §5.3의 검증 쿼리 1회 더 실행
-- payment 측 신규 가입자가 정말 없는지 (frozen 상태 재확인): MAX(id), COUNT(*) 변동 없음 확인
-- backend 측 staff 추가가 있었다면 매핑 테이블 갱신
```

### 7.2 user 매핑 테이블 생성 (payment DB)

§5.4의 SQL을 그대로 실행. `_user_id_mapping` 의 source 분포가
`auto=45, manual=2, shifted=2252` 인지 확인.

### 7.3 데이터 dump (payment DB)

```bash
# payment DB에서 shop 도메인 + user만 dump (data-only, --inserts로 멱등성 확보)
pg_dump --data-only --inserts \
  -t order_order \
  -t order_orderproductrelation \
  -t order_orderproductoptionrelation \
  -t order_singleproductcart \
  -t order_customerinfo \
  -t product_product \
  -t product_category \
  -t product_categorygroup \
  -t product_tag \
  -t product_producttagrelation \
  -t product_optiongroup \
  -t product_option \
  -t payment_history_paymenthistory \
  -t user_userext \
  -t auth_user_groups -t auth_user_user_permissions \
  -h <host> -U <user> -d <payment_db> \
  > /tmp/payment_dump.sql

# (history 테이블은 dump 대상에서 제외 — backend에서 새로 생성, TRUNCATE 상태로 시작)
```

### 7.4 dump 변환 (`_user_id_mapping` 적용)

권장: PR E에 `scripts/cutover_transform.py` 스크립트로 보관.

```python
# 1) payment DB에서 _user_id_mapping export
mapping = {row.payment_id: (row.backend_id, row.source) for row in fetchall()}

# 2) /tmp/payment_dump.sql 의 INSERT 문 파싱
#    - user_userext: source ∈ {'auto', 'manual'} 인 payment_id 의 row 는 건너뜀
#    - user_userext: source == 'shifted' 인 row 만 mapping[id]=backend_id 로 치환 후 보존
#    - shop 테이블의 user_id / created_by_id / updated_by_id / deleted_by_id 는
#      mapping 으로 일괄 치환
#    - auth_user_groups.user_id, auth_user_user_permissions.user_id 도 동일

# 3) /tmp/payment_dump_transformed.sql 로 출력
```

검증 포인트:
- 변환 전후 row 수: user_userext 만 2,299 → 2,252 (auto 45 + manual 2 = 47 감소)
- 변환 후 INSERT 문에 등장하는 user_id 의 distinct 개수가 backend 신규 + 매핑된 backend id 합과 일치

### 7.5 backend DB에 적용

```bash
# 0. 다운타임 시작 (backend 측만 — payment는 이미 frozen)

# 1. dump 적용 (변환된 SQL)
psql -h <host> -U <user> -d <backend_db> < /tmp/payment_dump_transformed.sql

# 2. Django 마이그레이션 history 정합 (테이블은 dump로 이미 생성/채워짐)
python manage.py migrate --fake shop_order
python manage.py migrate --fake shop_product
python manage.py migrate --fake shop_payment_history

# 3. simple-history 테이블 비우기 (이미 빈 상태일 텐데 보험)
psql -h <host> -U <user> -d <backend_db> -c "
  TRUNCATE order_historicalorderproductrelation,
           order_historicalcustomerinfo,
           order_historicalsingleproductcart,
           product_historicalcategory,
           product_historicalcategorygroup,
           product_historicalproducttagrelation,
           product_historicaloptiongroup
           RESTART IDENTITY;
"

# 4. 정합성 검증
python manage.py shell -c "
from shop.order.models import Order
from shop.payment_history.models import PaymentHistory
print(f'Orders: {Order.objects.count()}')
print(f'PaymentHistories: {PaymentHistory.objects.count()}')
"
python manage.py check
```

### 7.6 PortOne / 프론트엔드 전환

- PortOne 콘솔에서 webhook URL을 `https://shop-api.pycon.kr/...` 에서
  `https://rest-api.pycon.kr/v1/shop/...` 로 변경
- PortOne IP allowlist 가 backend 서버 IP를 포함하는지 확인
- 프론트엔드 (shop) 의 API base URL 도 backend로 전환 (배포는 별도)

### 7.7 골든패스 검증

- 어드민에서 임의 주문 조회 / sandbox 환불 dry-run
- 사용자 페이지에서 scancode/receipt URL 1건 확인

### 7.8 롤백

문제 발생 시:
- backend 측 `pg_restore --clean` 으로 dump 적용 전 상태 복구
- `migrate --fake zero shop_*` 로 마이그레이션 history 정리
- PortOne webhook URL 원복
- payment 측 데이터는 손대지 않았으므로 그대로 살아 있음

## 8. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| Allauth 쿠키/세션 정책이 backend 기존 정책과 충돌 | 로그인 회귀 | PR D 머지 전 staging에서 양쪽 로그인 플로우 모두 검증 |
| `core.openapi`와 `purchase_shared.utils.openapi` 충돌 | 빌드 실패 | PR A에서 한 번에 정리, diff 확인 |
| `migrate --fake` 후 `makemigrations`가 dirty diff 생성 | 마이그레이션 깨짐 | PR B에서 모델 정의를 payment와 100% 일치시키고 sandbox에서 사전 검증 |
| PortOne webhook IP allowlist | 환불 webhook 실패 | cutover 전 PortOne 콘솔에서 backend 서버 IP 등록 확인 |
| User PK 충돌 / email duplicate | INSERT 실패 또는 잘못된 매핑 | §5.3 검증 쿼리 결과 확인 후 변환 스크립트 보강 |
| simple-history `history_user_id` 가 가리키는 user 누락 | TRUNCATE으로 회피 (어차피 비울 예정) | 별도 대응 불필요 |
| `unique_id` 중복 (extremely 낮은 확률) | UNIQUE constraint 위반 | dump 변환 시 backend 기존 unique_id와 교집합 검사 → 충돌 시 재생성 |
| pg_dump의 INSERT 순서가 FK 의존성을 위반 | 적용 실패 | `pg_dump --disable-triggers` 또는 명시적 `SET session_replication_role = replica;` 사용 |
| 변환 스크립트 버그가 production 에서 발견 | 데이터 손상, 롤백 비용 | §7.0 dry-run 절차로 사전 차단. dry-run 실패 시 production 진입 금지 |

## 9. 작업 추정

| PR | 시간 | 난이도 |
|---|---|---|
| PR A 의존성·settings·core 인프라 | 1일 | 쉬움 |
| PR B shop sub-app + URL + 템플릿 + BaseAbstractModel 통합 | 1.5일 | 중간 |
| PR C admin_api endpoints | 1.5~2일 | 중간 |
| PR D User 병합 + Allauth + UserExt 갱신 | 1일 | 중간 |
| PR E 테스트·cutover 문서·SQL 변환 스크립트 | 1일 | 중간 |
| Cutover 실행 (다운타임) | 0.25~0.5일 | 중간 |
| **합계** | **6.25~7.25일** | **쉬움~중간** |

## 10. 진행 순서

PR A → PR B → (PR C ⊥ PR D 병행 가능) → PR E → Cutover.

PR C와 PR D는 PR B 완료 후 동시 진행 가능 (의존성 없음).

## Appendix A — backend `user_userext` (email, id) 페어

PR D 작업 / cutover 시점의 backend (`pyconkr_2025_prod_db`) staff/user 72명. §5.4의
자동 매칭 SQL `VALUES` 절에 그대로 사용. cutover 직전에 한 번 더 backend DB에서
재추출하여 변동분이 있으면 갱신할 것.

```sql
SELECT '(' || quote_literal(email) || ', ' || id || '),'
FROM user_userext ORDER BY id;
```

```
('system@python.or.kr', 0),
('musoftware@python.or.kr', 1),
('aineok0227@python.or.kr', 2),
('soyoung@python.or.kr', 3),
('jaehyuck.sa@python.or.kr', 4),
('darjeeling@python.or.kr', 5),
('golony6449@python.or.kr', 6),
('klou@python.or.kr', 7),
('lye@python.or.kr', 8),
('hanlee@python.or.kr', 9),
('cpprhtn@python.or.kr', 10),
('bluepicture08@python.or.kr', 11),
('steve.lee.dev@python.or.kr', 12),
('sudosubin@python.or.kr', 13),
('jungmir@python.or.kr', 14),
('jkyoon@python.or.kr', 15),
('pysong218@python.or.kr', 16),
('tiaz@python.or.kr', 17),
('hexff0000@python.or.kr', 18),
('kwanok@python.or.kr', 19),
('smkim12@python.or.kr', 20),
('hanuri714@python.or.kr', 21),
('hanjoo0211@python.or.kr', 22),
('simple-is-great@python.or.kr', 23),
('youn7054@python.or.kr', 24),
('sl@python.or.kr', 25),
('ppiyakk2@python.or.kr', 26),
('joongi@lablup.com', 27),
('importyha@gmail.com', 28),
('madsyntst@gmail.com', 29),
('bbchip13@gmail.com', 32),
('djccnt15@gmail.com', 33),
('channprj@gmail.com', 34),
('joeunpark@gmail.com', 35),
('oymggg@gmail.com', 36),
('yesys7777@gmail.com', 37),
('byundojin0216@gmail.com', 38),
('tmp_2@example.com', 39),
('nicebug@naver.com', 40),
('sytyactfhaha@gmail.com', 41),
('kyungjunlee.me@gmail.com', 42),
('ca3rot@gmail.com', 43),
('ksw@sionic.ai', 45),
('allen.k1m@kakaocorp.com', 46),
('world@worldsw.dev', 47),
('kdh1834@hufs.ac.kr', 48),
('jaewon.james.choi@gmail.com', 49),
('o3omoomin@gmail.com', 50),
('suitbread@gmail.com', 51),
('hightwinkle@naver.com', 52),
('s2460@e-mirim.hs.kr', 53),
('tmp_1@example.com', 54),
('jaeyeol.lee@hey.com', 55),
('nnoadev@gmail.com', 56),
('is9117@me.com', 57),
('gurwls223@apache.org', 58),
('hyewon.k.developer@gmail.com', 59),
('emscb@python.or.kr', 61),
('sniper45han@gmail.com', 62),
('donghee.na@python.org', 63),
('me@pyhub.kr', 64),
('haesunrpark@gmail.com', 65),
('krisnawatimelisa@gmail.com', 66),
('younghyun7248@gmail.com', 67),
('2chaes@gmail.com', 68),
('yssong@lablup.com', 69),
('jskang@lablup.com', 70),
('yonghoch@amazon.com', 71),
('yechoi@amazon.com', 72),
('bien@daangn.com', 73),
('johan@daangn.com', 74),
('session@email.com', 75)
```

note: id `30, 31, 44, 60` 은 결번 (이전 삭제). PK 시프트 offset 175 와 충돌하지
않으므로 영향 없음.

## Appendix B — 매뉴얼 매핑 테이블

도메인 변경 등으로 자동 매칭에서 누락된 동일인 매핑.

| payment_id | payment_email | payment_username | backend_id | backend_email | 비고 |
|---|---|---|---|---|---|
| 5 | darjeeling@gmail.com | kwon-han | 5 | darjeeling@python.or.kr | 동일인 (운영자 도메인 변경) |
| 1135 | darjeeling@gmail.com | darjeeling | 5 | darjeeling@python.or.kr | 동일인 (위와 같은 사람의 또 다른 계정) |

추가 케이스가 발생하면 cutover 전에 이 표에 행을 추가하고 §5.4의 (2) 매뉴얼 매핑 INSERT 에 반영할 것.

---

**다음 단계**: 본 plan에 대한 검토 후 OK 신호를 받으면 PR A 부터 작업을 시작한다.
