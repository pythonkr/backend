import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0005_event_stats_end_date_event_stats_start_date_and_more"),
        ("file", "0001_initial"),
    ]
    operations = [
        migrations.AddField(
            model_name="event",
            name="logo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="file.publicfile",
            ),
        ),
        migrations.AddField(
            model_name="historicalevent",
            name="logo",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="file.publicfile",
            ),
        ),
    ]
