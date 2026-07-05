from core.fields import EncryptedTextField
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("user", "0011_historicaluserext_merged_to_userext_merged_to_and_more")]
    operations = [
        migrations.AddField(
            model_name="userext",
            name="dooray_api_key",
            field=EncryptedTextField(
                blank=True,
                editable=False,
                key_setting_name="DOORAY_CRED_ENC_KEY",
                null=True,
            ),
        ),
    ]
