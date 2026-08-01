from __future__ import annotations

import secrets
import typing
from functools import cached_property
from uuid import uuid4

from core.const.system import SYSTEM_EMAIL, SYSTEM_USERNAME
from core.fields import EncryptedTextField
from core.scancode_mixin import ScanCodeMixin
from core.util.strutil import normalize_email
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class UserExtManager(UserManager):
    def _create_user(self, username, email, password, **extra_fields):
        user = super()._create_user(username, email, password, **extra_fields)
        if email:
            from allauth.account.models import EmailAddress

            EmailAddress.objects.get_or_create(
                user=user,
                email=email.lower(),
                defaults={"verified": True, "primary": True},
            )
        return user

    def filter_by_email(self, email: str) -> models.QuerySet[UserExt]:
        if not (email := normalize_email(email)):
            return self.none()
        return self.filter(models.Q(emailaddress__email__iexact=email) | models.Q(email__iexact=email)).distinct()

    def get_or_create_by_email(
        self, email: str, password: str | None = None, **extra_fields: typing.Any
    ) -> tuple[UserExt, bool]:
        email = normalize_email(email)
        candidates = self.filter_by_email(email).order_by("-is_active", "-date_joined")
        user = (
            candidates.filter(emailaddress__email__iexact=email, emailaddress__verified=True).first()
            or candidates.first()
        )
        if user is None:
            return self.create_by_email(email, password, **extra_fields), True

        seen: set[int] = set()  # 병합 대상 계정으로 해석. seen 은 비정상 병합 체인의 무한 루프 방어.
        while user.merged_to_id and user.pk not in seen:
            seen.add(user.pk)
            user = user.merged_to
        return user, False

    def create_by_email(self, email: str, password: str | None = None, **extra_fields: typing.Any) -> UserExt:
        email = normalize_email(email)
        if "username" not in extra_fields:
            max_length: int = self.model._meta.get_field("username").max_length
            local, _, domain = email.partition("@")
            username = local[:max_length]
            if self.filter(username=username).exists():
                username = (base := f"{domain}-{local}")[:max_length]
                while self.filter(username=username).exists():
                    suffix = f"-{secrets.token_hex(3)}"
                    username = base[: max_length - len(suffix)] + suffix
            extra_fields["username"] = username
        return self.create_user(email=email, password=password, **extra_fields)


class UserExt(ScanCodeMixin, AbstractUser):
    scancode_prefix = "user"
    scancode_uuid_field = "unique_id"

    choices_meta_schema: typing.ClassVar[dict] = {
        "email": {"label": "이메일", "type": "string", "filter": "search"},
        "nickname": {"label": "닉네임", "type": "string", "filter": "search"},
        "is_active": {"label": "활성", "type": "boolean"},
        "is_superuser": {"label": "스태프", "type": "boolean"},
    }

    image = models.ForeignKey("file.PublicFile", on_delete=models.PROTECT, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)
    unique_id = models.UUIDField(unique=True, editable=False, null=False, blank=False, default=uuid4)

    merged_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="merged_from")

    dooray_api_key = EncryptedTextField(key_setting_name="DOORAY_CRED_ENC_KEY", null=True, blank=True, editable=False)

    objects = UserExtManager()

    class Meta(AbstractUser.Meta):
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["unique_id"], name="userext_unique_id_idx")]

    def __str__(self):
        return f"[User] {self.nickname} <{self.email}>"

    def get_choice_meta(self) -> dict:
        return {
            "email": self.email,
            "nickname": self.nickname,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
        }

    @classmethod
    def get_system_user(cls) -> UserExt:
        return cls.objects.get_or_create(username=SYSTEM_USERNAME, email=SYSTEM_EMAIL)[0]

    @cached_property
    def emails(self) -> set[str]:
        emails = set(self.emailaddress_set.filter(verified=True).values_list("email", flat=True))
        if self.email:
            emails.add(self.email)

        return {e.lower() for e in emails}
