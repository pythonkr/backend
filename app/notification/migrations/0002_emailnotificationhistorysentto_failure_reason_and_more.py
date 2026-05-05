from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notification", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="emailnotificationhistorysentto",
            name="failure_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nhncloudkakaoalimtalknotificationhistorysentto",
            name="failure_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nhncloudsmsnotificationhistorysentto",
            name="failure_reason",
            field=models.TextField(blank=True, null=True),
        ),
    ]
