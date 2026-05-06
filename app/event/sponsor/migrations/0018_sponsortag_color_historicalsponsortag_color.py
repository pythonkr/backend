import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sponsor", "0017_alter_sponsor_options")]
    operations = [
        migrations.AddField(
            model_name="historicalsponsortag",
            name="color",
            field=models.CharField(
                blank=True,
                default="",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        message="색상은 #RGB 또는 #RRGGBB 형식의 hex 코드여야 합니다.",
                        regex="^#(?:[0-9a-fA-F]{3}){1,2}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="sponsortag",
            name="color",
            field=models.CharField(
                blank=True,
                default="",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        message="색상은 #RGB 또는 #RRGGBB 형식의 hex 코드여야 합니다.",
                        regex="^#(?:[0-9a-fA-F]{3}){1,2}$",
                    )
                ],
            ),
        ),
    ]
