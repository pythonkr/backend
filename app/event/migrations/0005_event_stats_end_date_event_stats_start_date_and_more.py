from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("event", "0004_remove_event_uq__evt__name_name_ko_and_more")]
    operations = [
        migrations.AddField(
            model_name="event",
            name="stats_end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="stats_start_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalevent",
            name="stats_end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalevent",
            name="stats_start_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
