"""DomainGroup 추가 + Sitemap.domain_group 연결 + DomainGroup.domains 그룹 간 중복 방지 trigger.

진행 순서:
1. (schema) DomainGroup / HistoricalDomainGroup 생성, Sitemap.domain_group 일시 nullable로 추가
2. (data) "2025년 PyConKR 홈페이지" 그룹 생성 후 모든 기존 Sitemap을 해당 그룹에 연결
3. (schema) Sitemap.domain_group을 NOT NULL로 변경, route_code unique constraint를 도메인 그룹 단위로 교체
4. (sql) DomainGroup.domains 그룹 간 중복을 막는 trigger + advisory lock 설치 — race-safe DB-level 강제
"""

import uuid

import django.contrib.postgres.fields
import django.contrib.postgres.indexes
import django.core.validators
import django.db.models.deletion
import simple_history.models
from core.const.regex import HOSTNAME_PATTERN
from django.conf import settings
from django.db import migrations, models

_HOSTNAME_MESSAGE = "올바른 호스트 형식이 아닙니다 (스킴/포트/경로/쿼리는 포함할 수 없습니다)."

DEFAULT_DOMAIN_GROUP_NAME = "2025년 PyConKR 홈페이지"
DEFAULT_DOMAIN_GROUP_DOMAINS = ["2025.pycon.kr"]

# advisory lock: READ COMMITTED 격리수준에서 동시 INSERT/UPDATE가 서로의 미커밋 row를 못 보는 문제를
# 해결하기 위해 모든 DomainGroup writer를 직렬화한다.
_CREATE_OVERLAP_TRIGGER = """
CREATE OR REPLACE FUNCTION cms_domain_group_check_overlap() RETURNS trigger AS $$
BEGIN
    IF NEW.deleted_at IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtext('cms_domaingroup_overlap'));
        IF EXISTS (
            SELECT 1 FROM cms_domaingroup
            WHERE id <> NEW.id
              AND deleted_at IS NULL
              AND domains && NEW.domains
        ) THEN
            RAISE EXCEPTION 'cms_domaingroup_domains_no_overlap'
            USING ERRCODE = 'unique_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cms_domaingroup_overlap_check
BEFORE INSERT OR UPDATE OF domains, deleted_at ON cms_domaingroup
FOR EACH ROW EXECUTE FUNCTION cms_domain_group_check_overlap();
"""

_DROP_OVERLAP_TRIGGER = """
DROP TRIGGER IF EXISTS cms_domaingroup_overlap_check ON cms_domaingroup;
DROP FUNCTION IF EXISTS cms_domain_group_check_overlap();
"""


def seed_default_domain_group(apps, schema_editor):
    DomainGroup = apps.get_model("cms", "DomainGroup")
    Sitemap = apps.get_model("cms", "Sitemap")

    group, _ = DomainGroup.objects.get_or_create(
        name=DEFAULT_DOMAIN_GROUP_NAME,
        defaults={"domains": DEFAULT_DOMAIN_GROUP_DOMAINS},
    )
    Sitemap.objects.filter(domain_group__isnull=True).update(domain_group=group)


def unseed_default_domain_group(apps, schema_editor):
    DomainGroup = apps.get_model("cms", "DomainGroup")
    Sitemap = apps.get_model("cms", "Sitemap")

    Sitemap.objects.filter(domain_group__name=DEFAULT_DOMAIN_GROUP_NAME).update(domain_group=None)
    DomainGroup.objects.filter(name=DEFAULT_DOMAIN_GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0012_alter_historicalsection_body_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1단계: 스키마 추가 (Sitemap.domain_group은 일시 nullable) ──────────────
        migrations.CreateModel(
            name="DomainGroup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(help_text="예: '2025년 PyConKR 홈페이지'", max_length=128)),
                (
                    "domains",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(
                            max_length=253,
                            validators=[
                                django.core.validators.RegexValidator(regex=HOSTNAME_PATTERN, message=_HOSTNAME_MESSAGE)
                            ],
                        ),
                        help_text="이 그룹에 속한 frontend 도메인 호스트 목록 (스킴/포트/경로 제외).",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_updated_by",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "deleted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_deleted_by",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.AddIndex(
            model_name="domaingroup",
            index=django.contrib.postgres.indexes.GinIndex(fields=["domains"], name="cms_domaing_domains_407bdc_gin"),
        ),
        migrations.AddConstraint(
            model_name="domaingroup",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("name",),
                name="uq__domain_group__name",
            ),
        ),
        migrations.CreateModel(
            name="HistoricalDomainGroup",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(help_text="예: '2025년 PyConKR 홈페이지'", max_length=128)),
                (
                    "domains",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(
                            max_length=253,
                            validators=[
                                django.core.validators.RegexValidator(regex=HOSTNAME_PATTERN, message=_HOSTNAME_MESSAGE)
                            ],
                        ),
                        help_text="이 그룹에 속한 frontend 도메인 호스트 목록 (스킴/포트/경로 제외).",
                    ),
                ),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "deleted_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical domain group",
                "verbose_name_plural": "historical domain groups",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.AddField(
            model_name="sitemap",
            name="domain_group",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sitemaps",
                to="cms.domaingroup",
                help_text="이 Sitemap이 노출될 frontend 도메인 그룹",
            ),
        ),
        migrations.AddField(
            model_name="historicalsitemap",
            name="domain_group",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="cms.domaingroup",
                help_text="이 Sitemap이 노출될 frontend 도메인 그룹",
            ),
        ),
        # ── 2단계: 데이터 마이그레이션 ───────────────────────────────────────
        migrations.RunPython(seed_default_domain_group, reverse_code=unseed_default_domain_group),
        # ── 3단계: NOT NULL로 변경 + unique constraint 교체 ──────────────────
        migrations.AlterField(
            model_name="sitemap",
            name="domain_group",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sitemaps",
                to="cms.domaingroup",
                help_text="이 Sitemap이 노출될 frontend 도메인 그룹",
            ),
        ),
        migrations.RemoveConstraint(model_name="sitemap", name="uq__sitemap__parent_route_code"),
        migrations.AddConstraint(
            model_name="sitemap",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("domain_group", "parent_sitemap", "route_code"),
                name="uq__sitemap__domain_parent_route_code",
            ),
        ),
        # ── 4단계: race-safe DB-level 중복 방지 trigger ────────────────────
        migrations.RunSQL(sql=_CREATE_OVERLAP_TRIGGER, reverse_sql=_DROP_OVERLAP_TRIGGER),
    ]
