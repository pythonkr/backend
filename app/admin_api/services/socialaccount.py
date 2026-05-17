from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.db import transaction
from django.db.models import QuerySet


def delete_social_accounts_and_cleanup_user_emails(social_accounts: QuerySet[SocialAccount]) -> None:
    with transaction.atomic():
        if not (affected_user_ids := set(social_accounts.values_list("user_id", flat=True))):
            return
        social_accounts.delete()
        EmailAddress.objects.filter(user_id__in=affected_user_ids).exclude(
            user_id__in=SocialAccount.objects.filter(user_id__in=affected_user_ids).values("user_id")
        ).delete()
