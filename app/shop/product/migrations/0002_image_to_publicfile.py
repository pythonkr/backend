import django.db.models.deletion
from django.db import migrations, models

# 사전 계산값. 새 URL 이 발견되면 여기에 추가하거나 RunPython 결과를 확인할 것.
LEGACY_IMAGE_META: dict[str, dict] = {
    "https://s3.ap-northeast-2.amazonaws.com/pyconkr-backend-prod-public/public/t-shirt-compressed.png": {
        "file_path": "public/t-shirt-compressed.png",
        "hash": "d131452cf6cd2287e4c302f4f7c17bb5",
        "size": 2069683,
        "mimetype": "image/png",
    },
    "https://s3.ap-northeast-2.amazonaws.com/pyconkr-backend-prod-public/public/t-shirt-comporessed-2.png": {
        "file_path": "public/t-shirt-comporessed-2.png",
        "hash": "30acab0125661cac1ce75c4a4633042a",
        "size": 2278886,
        "mimetype": "image/png",
    },
}


def _migrate_image_urls(apps, schema_editor) -> None:
    Product = apps.get_model("product", "Product")
    PublicFile = apps.get_model("file", "PublicFile")

    unknown_urls: list[tuple[str, str]] = []
    for product in Product.objects.exclude(image__isnull=True).exclude(image="").iterator():
        url = product.image
        meta = LEGACY_IMAGE_META.get(url)
        if not meta:
            unknown_urls.append((str(product.id), url))
            continue
        public_file, _ = PublicFile.objects.get_or_create(
            file=meta["file_path"],
            defaults={"hash": meta["hash"], "size": meta["size"], "mimetype": meta["mimetype"]},
        )
        product.image_publicfile = public_file
        product.save(update_fields=["image_publicfile"])

    if unknown_urls:
        # 끊은 채로 진행 (admin 수동 정정 가능) — 단, 잊지 않도록 stdout 로 알림.
        print(f"[migration product.0002] {len(unknown_urls)} unknown image URL(s) — image FK left NULL: {unknown_urls}")


def _noop_reverse(apps, schema_editor) -> None:
    pass


class Migration(migrations.Migration):
    atomic = True  # 다단계 operation 중간 실패 시 컬럼 추가/제거 + 데이터 이관 일괄 롤백.
    dependencies = [("file", "0001_initial"), ("product", "0001_initial")]
    operations = [
        # 1) 신규 FK 컬럼 추가
        migrations.AddField(
            model_name="product",
            name="image_publicfile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="file.publicfile",
                verbose_name="대표 이미지",
            ),
        ),
        migrations.AddField(
            model_name="historicalproduct",
            name="image_publicfile",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="file.publicfile",
                verbose_name="대표 이미지",
            ),
        ),
        # 2) URL → PublicFile 매핑
        migrations.RunPython(_migrate_image_urls, _noop_reverse),
        # 3) 구 URLField 컬럼 제거
        migrations.RemoveField(model_name="product", name="image"),
        migrations.RemoveField(model_name="historicalproduct", name="image"),
        # 4) image_publicfile → image
        migrations.RenameField(model_name="product", old_name="image_publicfile", new_name="image"),
        migrations.RenameField(model_name="historicalproduct", old_name="image_publicfile", new_name="image"),
    ]
