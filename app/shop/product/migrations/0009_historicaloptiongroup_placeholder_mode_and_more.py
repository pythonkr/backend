from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("product", "0008_alter_historicalproduct_refundable_ends_at_and_more")]
    operations = [
        migrations.AddField(
            model_name="historicaloptiongroup",
            name="placeholder_mode",
            field=models.CharField(
                choices=[
                    ("hidden", "선택해주세요 미노출"),
                    ("optional", "노출, 선택해도 통과"),
                    ("required", "노출, 선택 시 검증 실패"),
                ],
                default="hidden",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="optiongroup",
            name="placeholder_mode",
            field=models.CharField(
                choices=[
                    ("hidden", "선택해주세요 미노출"),
                    ("optional", "노출, 선택해도 통과"),
                    ("required", "노출, 선택 시 검증 실패"),
                ],
                default="hidden",
                max_length=10,
            ),
        ),
    ]
