import core.models
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("sponsor", "0018_remove_sponsor_uq__spsr__name_name_ko_and_more")]
    operations = [
        migrations.AddField(
            model_name="historicalsponsortag",
            name="color",
            field=core.models.ColorField(
                blank=True,
                default=None,
                help_text="태그 표시 색상 (예: #3498db). 지정하지 않으면 프론트엔드 기본색을 사용합니다.",
                max_length=7,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="sponsortag",
            name="color",
            field=core.models.ColorField(
                blank=True,
                default=None,
                help_text="태그 표시 색상 (예: #3498db). 지정하지 않으면 프론트엔드 기본색을 사용합니다.",
                max_length=7,
                null=True,
            ),
        ),
    ]
