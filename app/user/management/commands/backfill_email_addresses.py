from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.core.management.base import BaseCommand, CommandParser
from user.models import UserExt


class Command(BaseCommand):
    help = "비소셜·활성·이메일 있음이면서 EmailAddress 가 없는 계정에 EmailAddress(verified·primary)를 백필한다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--apply", action="store_true", help="실제 생성 (기본은 dry-run)")

    def handle(self, *args: object, **options: object) -> None:
        candidates = (
            UserExt.objects.filter(is_active=True)
            .exclude(email="")
            .exclude(email__isnull=True)
            .exclude(pk__in=SocialAccount.objects.values("user_id"))
            .exclude(pk__in=EmailAddress.objects.values("user_id"))
        )
        rows = [EmailAddress(user=user, email=user.email.lower(), verified=True, primary=True) for user in candidates]

        by_email: dict[str, list] = {}
        for row in rows:
            by_email.setdefault(row.email, []).append(row.user_id)
        if dupes := {email: uids for email, uids in by_email.items() if len(uids) > 1}:
            self.stdout.write(
                self.style.WARNING(f"여러 계정이 같은 email 사용 {len(dupes)}건 (verified 충돌로 일부만 생성됨)")
            )

        if not options["apply"]:
            self.stdout.write(f"[dry-run] 생성 예정 EmailAddress {len(rows)}건 — 실제 생성하려면 --apply")
            return

        created = EmailAddress.objects.bulk_create(rows, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"EmailAddress {len(created)}건 생성 완료"))
