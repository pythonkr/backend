"""기존 티켓 OPR 의 참가자 정보(custom-response 옵션)를 TicketInfo 로 백필.

옵션 그룹명 → TicketInfo 필드 매핑:
  이름     ← "성함..."(예: "성함", "성함 (티켓에 표시되는 이름)")
  소속     ← "소속"
  이메일    ← "이메일"
  연락처    ← "연락처..." 또는 "전화번호"
  후원자 멘트 ← "후원자..."(예: "후원자의 한마디를 남겨주세요!")
이름이 비어있는(미완성) OPR 은 건너뛴다. 멱등 — 이미 TicketInfo 가 있는 OPR 은 skip.

이관이 끝난 옵션 응답(OrderProductOptionRelation)은 **soft-delete** 한다(데이터는 TicketInfo 로 옮겨졌으므로
중복). 롤백(reverse) 시 그 옵션들을 **복원**(deleted_at 해제)하고 TicketInfo 를 제거 — 원본 행을 그대로 되살린다.
"""

from __future__ import annotations

from collections import defaultdict

from django.db import migrations
from django.db.models.functions import Now

BATCH_SIZE = 1000


def _classify(group_name: str) -> str | None:
    if group_name.startswith("성함"):
        return "name"
    if group_name == "소속":
        return "organization"
    if group_name == "이메일":
        return "email"
    if group_name.startswith("연락처") or group_name == "전화번호":
        return "phone"
    if group_name.startswith("후원자"):
        return "contribution_message"
    return None


def backfill_ticket_info(apps, schema_editor):
    OrderProductRelation = apps.get_model("order", "OrderProductRelation")
    OrderProductOptionRelation = apps.get_model("order", "OrderProductOptionRelation")
    TicketInfo = apps.get_model("order", "TicketInfo")

    ticket_opr_ids = list(
        OrderProductRelation.objects.filter(
            deleted_at__isnull=True,
            product__category__is_ticket=True,
        ).values_list("id", flat=True)
    )
    if not ticket_opr_ids:
        return

    already_has = set(
        TicketInfo.objects.filter(deleted_at__isnull=True).values_list("order_product_relation_id", flat=True)
    )

    responses: dict[object, dict[str, str]] = defaultdict(dict)
    migrated_opors: dict[object, list[object]] = defaultdict(list)  # opr_id -> 이관 대상 OPOR id 목록
    option_rows = OrderProductOptionRelation.objects.filter(
        deleted_at__isnull=True,
        order_product_relation__deleted_at__isnull=True,
        order_product_relation__product__category__is_ticket=True,
        product_option_group__is_custom_response=True,
    ).values_list("id", "order_product_relation_id", "product_option_group__name", "custom_response")
    for opor_id, opr_id, group_name, custom_response in option_rows.iterator():
        field = _classify(group_name)
        if field is None:
            continue
        migrated_opors[opr_id].append(opor_id)
        value = (custom_response or "").strip()
        # 같은 필드에 매핑되는 그룹이 여럿이면 비어있지 않은 값을 우선.
        if value or field not in responses[opr_id]:
            responses[opr_id][field] = value

    to_create = []
    opor_ids_to_soft_delete: list[object] = []
    for opr_id in ticket_opr_ids:
        if opr_id in already_has:
            continue
        data = responses.get(opr_id, {})
        name = data.get("name", "")
        if not name:  # 이름 없는 미완성 OPR 은 건너뜀.
            continue
        to_create.append(
            TicketInfo(
                order_product_relation_id=opr_id,
                name=name,
                phone=data.get("phone", ""),
                email=data.get("email", ""),
                organization=data.get("organization") or None,
                contribution_message=data.get("contribution_message") or None,
            )
        )
        opor_ids_to_soft_delete.extend(migrated_opors.get(opr_id, []))

    TicketInfo.objects.bulk_create(to_create, batch_size=BATCH_SIZE)

    # 이관 완료된 옵션 응답은 soft-delete (reverse 에서 복원).
    for start in range(0, len(opor_ids_to_soft_delete), BATCH_SIZE):
        end = start + BATCH_SIZE
        OrderProductOptionRelation.objects.filter(id__in=opor_ids_to_soft_delete[start:end]).update(deleted_at=Now())


def restore_migrated_options(apps, schema_editor):
    OrderProductOptionRelation = apps.get_model("order", "OrderProductOptionRelation")
    TicketInfo = apps.get_model("order", "TicketInfo")

    # backfill 때 soft-delete 한 옵션 응답을 복원 — TicketInfo 가 있는 OPR 의 매핑(이관) 대상 custom-response 옵션 중 soft-deleted 인 것.
    ti_opr_ids = list(TicketInfo.objects.values_list("order_product_relation_id", flat=True))
    if ti_opr_ids:
        deleted_rows = OrderProductOptionRelation.objects.filter(
            deleted_at__isnull=False,
            order_product_relation_id__in=ti_opr_ids,
            product_option_group__is_custom_response=True,
        ).values_list("id", "product_option_group__name")
        restore_ids = [opor_id for opor_id, group_name in deleted_rows if _classify(group_name) is not None]
        for start in range(0, len(restore_ids), BATCH_SIZE):
            end = start + BATCH_SIZE
            OrderProductOptionRelation.objects.filter(id__in=restore_ids[start:end]).update(deleted_at=None)

    TicketInfo.objects.all().delete()


class Migration(migrations.Migration):
    atomic = True
    dependencies = [
        ("order", "0004_historicalticketinfo_ticketinfo"),
        ("product", "0006_category_is_ticket_historicalcategory_is_ticket"),
    ]
    operations = [migrations.RunPython(backfill_ticket_info, restore_migrated_options)]
