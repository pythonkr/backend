import user.models.user
from django.db.migrations import AlterModelManagers
from django.db.migrations import Migration as DjangoMigrations


class Migration(DjangoMigrations):
    dependencies = [("user", "0013_usermergeemailsnapshot")]
    operations = [AlterModelManagers(name="userext", managers=[("objects", user.models.user.UserExtManager())])]
