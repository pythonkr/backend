from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notification", "0002_emailnotificationhistorysentto_failure_reason_and_more")]
    operations = [
        migrations.AddField(
            model_name="emailnotificationtemplate",
            name="editor_source",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nhncloudkakaoalimtalknotificationtemplate",
            name="editor_source",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nhncloudsmsnotificationtemplate",
            name="editor_source",
            field=models.TextField(blank=True, null=True),
        ),
    ]
