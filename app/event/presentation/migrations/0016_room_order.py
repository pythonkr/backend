from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("presentation", "0015_remove_presentationcategory_uq__prst_cat__type__name_name_ko_and_more")]
    operations = [migrations.AddField(model_name="room", name="order", field=models.IntegerField(default=0))]
