"""python-korea-payment legacy DB → backend DB 데이터 이관.

Cutover 시 `LEGACY_DATABASE_NAME` 환경변수가 설정되어 있을 때만 실행됩니다.
미설정 시 no-op — 개발/테스트 환경 및 cutover 완료 후 재실행 모두 안전.
같은 Postgres 인스턴스를 전제로 host/port/user/password 는 default DB 재사용 (backend user 에 legacy DB SELECT 권한 GRANT 필요).

이관 대상:
- user_userext: legacy-only (shifted) 사용자 INSERT + 매칭된 사용자 unique_id 갱신 (QR 연속성).
- socialaccount_socialapp: provider 설정 (github/google/kakao/naver client_id 등 — backend 가 빈 상태라 그대로 복사).
- socialaccount_socialaccount, account_emailaddress: allauth 로그인 연속성 (kakao/google/naver 로 재로그인 시 동일 사용자로 매칭).
- product_*: CategoryGroup → Category → Tag → Product → OptionGroup → Option → ProductTagRelation
- order_*: Order → OrderProductRelation → OrderProductOptionRelation → SingleProductCart → CustomerInfo
- payment_history_paymenthistory
- *historical*: simple-history 보존 (admin audit trail)

이관 제외:
- payment_payment (deprecated, 사용처 0)
- user_userext_groups, user_userext_user_permissions (auth 정책 변경 — admin 재설정)
- socialaccount_socialtoken (만료 토큰 — 다음 로그인 시 새 발급; legacy 측 0 rows)
- account_emailconfirmation (만료 단발 토큰)
- openid_openidnonce, openid_openidstore (legacy 측 0 rows)
- auth_*, authtoken_*, django_*, usersessions_*: backend 기준으로 통일

User 매핑 우선순위 (총 2,299명):
- auto_email: email 정규화 (@pycon.kr → @python.or.kr) 매칭
- auto_username: 위 미매칭 + username 동일 (같은 사람이 다른 email 로 양쪽 가입한 케이스)
- manual: hardcoded — darjeeling@gmail.com (legacy id 5, 1135) → backend darjeeling@python.or.kr (id 5)
- shifted: 모두 미매칭 → legacy.id + USER_ID_OFFSET (backend max id 와 충돌 없는 여유 공간)
"""

from enum import StrEnum

from django.db import connections, migrations, transaction

EMAIL_REWRITE_OLD = "@pycon.kr"
EMAIL_REWRITE_NEW = "@python.or.kr"
USER_ID_OFFSET = 175
MANUAL_USER_MAPPING: dict[int, int] = {5: 5, 1135: 5}
BATCH_SIZE = 1000


class _Source(StrEnum):
    AUTO_EMAIL = "auto_email"
    AUTO_USERNAME = "auto_username"
    MANUAL = "manual"
    SHIFTED = "shifted"


_BASE_USER_FK = frozenset({"created_by_id", "updated_by_id", "deleted_by_id"})
_HISTORY_USER_FK = _BASE_USER_FK | {"history_user_id"}

# Topological INSERT 순서 (FK 의존성). user_fk_cols 의 컬럼 값은 user_id_map 으로 변환됨.
TABLES_TO_COPY: list[tuple[str, frozenset[str]]] = [
    # allauth — 로그인 연속성 + provider 설정
    ("socialaccount_socialapp", frozenset()),  # provider config (github/google/kakao/naver, FK 없음)
    ("socialaccount_socialaccount", frozenset({"user_id"})),
    ("account_emailaddress", frozenset({"user_id"})),
    # shop product
    ("product_categorygroup", _BASE_USER_FK),
    ("product_category", _BASE_USER_FK),
    ("product_tag", _BASE_USER_FK),
    ("product_product", _BASE_USER_FK),
    ("product_optiongroup", _BASE_USER_FK),
    ("product_option", _BASE_USER_FK),
    ("product_producttagrelation", _BASE_USER_FK),
    ("order_order", _BASE_USER_FK | {"user_id"}),
    ("order_orderproductrelation", _BASE_USER_FK),
    ("order_singleproductcart", _BASE_USER_FK | {"user_id"}),
    ("order_orderproductoptionrelation", _BASE_USER_FK),
    ("order_customerinfo", _BASE_USER_FK),
    ("payment_history_paymenthistory", _BASE_USER_FK),
    # historical_* 는 FK 제약 없음 — 순서 임의. 가독성 위해 위와 동일 순서.
    ("product_historicalcategorygroup", _HISTORY_USER_FK),
    ("product_historicalcategory", _HISTORY_USER_FK),
    ("product_historicaltag", _HISTORY_USER_FK),
    ("product_historicalproduct", _HISTORY_USER_FK),
    ("product_historicaloptiongroup", _HISTORY_USER_FK),
    ("product_historicaloption", _HISTORY_USER_FK),
    ("product_historicalproducttagrelation", _HISTORY_USER_FK),
    ("order_historicalorder", _HISTORY_USER_FK | {"user_id"}),
    ("order_historicalorderproductrelation", _HISTORY_USER_FK),
    ("order_historicalsingleproductcart", _HISTORY_USER_FK | {"user_id"}),
    ("order_historicalorderproductoptionrelation", _HISTORY_USER_FK),
    ("order_historicalcustomerinfo", _HISTORY_USER_FK),
]


def _normalize_email(email: str | None) -> str | None:
    if not email:
        return email
    lower = email.lower()
    return lower.removesuffix(EMAIL_REWRITE_OLD) + EMAIL_REWRITE_NEW if lower.endswith(EMAIL_REWRITE_OLD) else lower


def _build_user_id_map(target_cur, legacy_cur) -> dict[int, tuple[int, _Source]]:
    """legacy.user_userext.id → (target.id, source) 매핑 구성."""
    target_cur.execute("SELECT id, email, username FROM public.user_userext")
    backend_rows = target_cur.fetchall()
    backend_by_email = {_normalize_email(email): pk for pk, email, _ in backend_rows}
    backend_by_username = {username: pk for pk, _, username in backend_rows}

    legacy_cur.execute("SELECT id, email, username FROM public.user_userext")
    mapping: dict[int, tuple[int, _Source]] = {}
    username_matches: list[tuple[int, str, int]] = []
    for legacy_id, email, username in legacy_cur.fetchall():
        if (backend_id := backend_by_email.get(_normalize_email(email))) is not None:
            mapping[legacy_id] = (backend_id, _Source.AUTO_EMAIL)
        elif (backend_id := backend_by_username.get(username)) is not None:
            mapping[legacy_id] = (backend_id, _Source.AUTO_USERNAME)
            username_matches.append((legacy_id, username, backend_id))
        elif legacy_id in MANUAL_USER_MAPPING:
            mapping[legacy_id] = (MANUAL_USER_MAPPING[legacy_id], _Source.MANUAL)
        else:
            mapping[legacy_id] = (legacy_id + USER_ID_OFFSET, _Source.SHIFTED)

    counts: dict[str, int] = {s.value: 0 for s in _Source}
    for _, src in mapping.values():
        counts[src] += 1
    print(f"[migrate_legacy] user_id_map: total={len(mapping)}, {counts}")
    # username-only 매칭은 동일인일 확률이 높지만 false positive 가능 — 운영자 검토용 로그.
    if username_matches:
        print(f"[migrate_legacy] username-only matches ({len(username_matches)}건, 검토 권장):")
        for lid, username, bid in username_matches:
            print(f"  legacy.id={lid} username={username!r} → backend.id={bid}")
    return mapping


def _copy_shifted_users(target_cur, legacy_cur, user_id_map: dict[int, tuple[int, _Source]]) -> None:
    shifted_ids = [lid for lid, (_, src) in user_id_map.items() if src == _Source.SHIFTED]
    if not shifted_ids:
        return
    legacy_cur.execute(
        """
        SELECT id, password, last_login, is_superuser, username,
               first_name, last_name, email, is_staff, is_active, date_joined, unique_id
        FROM public.user_userext WHERE id = ANY(%s) ORDER BY id
        """,
        [shifted_ids],
    )
    # legacy 에는 nickname 컬럼이 없음 — username 으로 ko/en 기본값 채우기 (master nickname 은 None).
    # image_id 도 legacy 부재.
    rows = [
        (user_id_map[lid][0], pw, llg, sup, uname, fn, ln, em, stf, act, dj, None, uname, uname, None, uniq)
        for lid, pw, llg, sup, uname, fn, ln, em, stf, act, dj, uniq in legacy_cur.fetchall()
    ]
    target_cur.executemany(
        """
        INSERT INTO public.user_userext (
            id, password, last_login, is_superuser, username,
            first_name, last_name, email, is_staff, is_active, date_joined,
            nickname, nickname_en, nickname_ko, image_id, unique_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )


def _update_matched_unique_id(target_cur, legacy_cur, user_id_map: dict[int, tuple[int, _Source]]) -> None:
    """auto/manual 매칭된 사용자의 unique_id 를 legacy 값으로 덮어쓴다 — payment 시절 발급된 QR/토큰 연속성 유지."""
    matched = [(lid, bid) for lid, (bid, src) in user_id_map.items() if src != _Source.SHIFTED]
    if not matched:
        return
    legacy_cur.execute(
        "SELECT id, unique_id FROM public.user_userext WHERE id = ANY(%s)",
        [[lid for lid, _ in matched]],
    )
    legacy_unique = dict(legacy_cur.fetchall())
    updates = [(legacy_unique[lid], bid) for lid, bid in matched if lid in legacy_unique]
    target_cur.executemany("UPDATE public.user_userext SET unique_id = %s WHERE id = %s", updates)


def _get_columns(cur, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        [table],
    )
    return [r[0] for r in cur.fetchall()]


def _copy_account_emailaddress(target_cur, legacy_cur, user_id_map: dict[int, tuple[int, _Source]]) -> None:
    """account_emailaddress 전용 — `(user_id, primary=true)` 부분 unique index 충돌 회피.

    같은 backend user 로 매핑된 여러 legacy email 이 모두 primary 인 경우 (merge 케이스),
    첫 항목만 primary 유지, 나머지는 primary=false 로 demote.
    """
    legacy_cur.execute(
        'SELECT id, email, verified, "primary", user_id FROM public.account_emailaddress '
        'ORDER BY user_id, "primary" DESC, id'
    )
    seen_primary: set[int] = set()
    rows = []
    for row_id, email, verified, is_primary, legacy_uid in legacy_cur.fetchall():
        backend_uid = user_id_map[legacy_uid][0]
        if is_primary and backend_uid in seen_primary:
            is_primary = False  # 같은 backend user 의 두 번째 primary 는 demote
        elif is_primary:
            seen_primary.add(backend_uid)
        rows.append((row_id, email, verified, is_primary, backend_uid))
    target_cur.executemany(
        'INSERT INTO public.account_emailaddress (id, email, verified, "primary", user_id) VALUES (%s, %s, %s, %s, %s)',
        rows,
    )
    print(f"[migrate_legacy] account_emailaddress: copied {len(rows)} rows")


def _copy_table(
    target_cur, legacy_cur, table: str, user_fk_cols: frozenset[str], user_id_map: dict[int, tuple[int, _Source]]
) -> None:
    legacy_cols = _get_columns(legacy_cur, table)
    target_cols = set(_get_columns(target_cur, table))
    if not legacy_cols or not target_cols:
        raise RuntimeError(
            f"Table {table} missing in legacy ({len(legacy_cols)} cols) or target ({len(target_cols)} cols)"
        )
    # legacy ∩ target 컬럼만 (스키마 drift 방어). 순서는 legacy 기준.
    cols = [c for c in legacy_cols if c in target_cols]
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    fk_indices = [i for i, c in enumerate(cols) if c in user_fk_cols]

    # nosec: B608 — TABLES_TO_COPY 화이트리스트 + information_schema 컬럼명, 사용자 입력 없음
    select_sql = f"SELECT {col_list} FROM public.{table}"  # nosec: B608
    insert_sql = f"INSERT INTO public.{table} ({col_list}) VALUES ({placeholders})"  # nosec: B608
    legacy_cur.execute(select_sql)
    total = 0
    while batch := legacy_cur.fetchmany(BATCH_SIZE):
        translated = []
        for row in batch:
            row = list(row)
            # mapping 누락 시 그대로 둬서 FK 위반으로 detect — 모든 user 가 mapping 에 포함되어야 정상.
            for idx in fk_indices:
                if row[idx] is not None and row[idx] in user_id_map:
                    row[idx] = user_id_map[row[idx]][0]
            translated.append(tuple(row))
        target_cur.executemany(insert_sql, translated)
        total += len(translated)
    print(f"[migrate_legacy] {table}: copied {total} rows")


def _reset_sequences(target_cur) -> None:
    """수동 INSERT 후 IDENTITY/SEQUENCE 컬럼을 max+1 로 동기화 — 다음 INSERT 충돌 방지."""
    targets = [
        ("user_userext", "id"),
        ("socialaccount_socialapp", "id"),
        ("socialaccount_socialaccount", "id"),
        ("account_emailaddress", "id"),
        *((table, "history_id") for table, _ in TABLES_TO_COPY if "historical" in table),
    ]
    for table, pk_col in targets:
        # hardcoded 테이블/컬럼명, 사용자 입력 없음
        seq_expr = f"pg_get_serial_sequence('public.{table}', '{pk_col}')"  # nosec: B608
        max_expr = f"(SELECT MAX({pk_col}) FROM public.{table})"  # nosec: B608
        target_cur.execute(f"SELECT setval({seq_expr}, COALESCE({max_expr}, 1), true)")  # nosec: B608


def _verify(target_cur, legacy_cur) -> None:
    """legacy 와 target 의 row count 비교."""
    mismatches = []
    for table, _ in TABLES_TO_COPY:
        # nosec: B608 — TABLES_TO_COPY 는 화이트리스트
        legacy_cur.execute(f"SELECT COUNT(*) FROM public.{table}")  # nosec: B608
        legacy_count = legacy_cur.fetchone()[0]
        target_cur.execute(f"SELECT COUNT(*) FROM public.{table}")  # nosec: B608
        target_count = target_cur.fetchone()[0]
        if legacy_count != target_count:
            mismatches.append(f"{table}: legacy={legacy_count}, target={target_count}")
    if mismatches:
        raise RuntimeError("Row count mismatch:\n  " + "\n  ".join(mismatches))


def migrate_data(apps, schema_editor):
    if "legacy" not in connections.databases:
        return  # 개발/테스트 환경 또는 cutover 완료 후 — no-op.

    # 중간 실패 시 target DB 의 모든 변경을 함께 롤백 (legacy DB 는 SELECT 만 — 롤백 불필요).
    with (
        transaction.atomic(using="default"),
        connections["legacy"].cursor() as legacy_cur,
        connections["default"].cursor() as target_cur,
    ):
        user_id_map = _build_user_id_map(target_cur, legacy_cur)
        _copy_shifted_users(target_cur, legacy_cur, user_id_map)
        _update_matched_unique_id(target_cur, legacy_cur, user_id_map)

        for table, user_fk_cols in TABLES_TO_COPY:
            if table == "account_emailaddress":
                _copy_account_emailaddress(target_cur, legacy_cur, user_id_map)
            else:
                _copy_table(target_cur, legacy_cur, table, user_fk_cols, user_id_map)

        _reset_sequences(target_cur)
        _verify(target_cur, legacy_cur)


class Migration(migrations.Migration):
    atomic = True
    dependencies = [
        ("user", "0009_alter_historicaluserext_options_and_more"),
        ("order", "0001_initial"),
        ("product", "0001_initial"),
        ("payment_history", "0001_initial"),
        # allauth — socialaccount/account 테이블 선행 생성
        ("socialaccount", "0006_alter_socialaccount_extra_data"),
        ("account", "0009_emailaddress_unique_primary_email"),
    ]
    operations = [migrations.RunPython(migrate_data, reverse_code=migrations.RunPython.noop)]
