import collections.abc
import contextlib
import typing
import uuid
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.models import AutoField, TextField, UUIDField, expressions, fields
from django.db.models.fields.reverse_related import ForeignObjectRel

BaseDatabaseOperations.integer_field_ranges["UUIDField"] = (0, 0)

_ValidatorCallable: typing.TypeAlias = collections.abc.Callable[[typing.Any], None]
_Choice: typing.TypeAlias = tuple[typing.Any, typing.Any]
_ChoiceNamedGroup: typing.TypeAlias = tuple[str, collections.abc.Iterable[_Choice]]
_Choices: typing.TypeAlias = collections.abc.Iterable[_Choice | _ChoiceNamedGroup]


class UUIDFieidInitKwargs(typing.TypedDict):
    name: typing.NotRequired[str | None]
    primary_key: typing.NotRequired[bool]
    max_length: typing.NotRequired[int | None]
    unique: typing.NotRequired[bool]
    blank: typing.NotRequired[bool]
    null: typing.NotRequired[bool]
    db_index: typing.NotRequired[bool]
    rel: typing.NotRequired[ForeignObjectRel | None]
    default: typing.NotRequired[typing.Any]
    db_default: typing.NotRequired[type[fields.NOT_PROVIDED] | expressions.Expression | typing.Any]
    editable: typing.NotRequired[bool]
    serialize: typing.NotRequired[bool]
    unique_for_date: typing.NotRequired[str | None]
    unique_for_month: typing.NotRequired[str | None]
    unique_for_year: typing.NotRequired[str | None]
    choices: typing.NotRequired[_Choices | None]
    help_text: typing.NotRequired[str]
    db_column: typing.NotRequired[str | None]
    db_comment: typing.NotRequired[str | None]
    db_tablespace: typing.NotRequired[str | None]
    auto_created: typing.NotRequired[bool]
    validators: typing.NotRequired[collections.abc.Iterable[_ValidatorCallable]]
    error_messages: typing.NotRequired[dict[str, typing.Any] | None]


class UUIDAutoField(UUIDField, AutoField):
    _pyi_private_set_type: uuid.UUID  # type: ignore[assignment]
    _pyi_private_get_type: uuid.UUID  # type: ignore[assignment]
    _pyi_lookup_exact_type: uuid.UUID  # type: ignore[assignment]

    def __init__(self, verbose_name: str | None = None, **kwargs: typing.Unpack[UUIDFieidInitKwargs]) -> None:
        kwargs.setdefault("default", uuid.uuid4)
        kwargs.setdefault("editable", False)
        super().__init__(verbose_name, **kwargs)

    def _check_max_length_warning(self) -> list[str]:
        return []

    def get_prep_value(self, value: typing.Any) -> uuid.UUID | None:
        if value in (None, "") or isinstance(value, uuid.UUID):
            return None
        if isinstance(value, str):
            return uuid.UUID(value)
        if isinstance(value, bytes):
            return uuid.UUID(bytes=value)
        if isinstance(value, int):
            return uuid.UUID(int=value)
        if isinstance(value, collections.abc.Sequence):
            return uuid.UUID(bytes=bytes(value))
        with contextlib.suppress(ValueError):
            return uuid.UUID(value)
        return self.to_python(value)


@lru_cache(maxsize=None)
def _build_fernet(key_setting_name: str) -> MultiFernet:
    raw = getattr(settings, key_setting_name, "") or ""
    if not (keys := [k.strip() for k in raw.split(",") if k.strip()]):
        raise ImproperlyConfigured(f"{key_setting_name} 미설정 (Fernet 키 필수).")
    return MultiFernet([Fernet(k) for k in keys])


class EncryptedTextField(TextField):
    def __init__(self, *args: typing.Any, key_setting_name: str, **kwargs: typing.Any) -> None:
        self.key_setting_name = key_setting_name
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple:
        name, path, args, kwargs = super().deconstruct()
        kwargs["key_setting_name"] = self.key_setting_name
        return name, path, args, kwargs

    def _fernet(self) -> MultiFernet:
        return _build_fernet(self.key_setting_name)

    def check(self, **kwargs: typing.Any) -> list:
        errors = super().check(**kwargs)
        if not (getattr(settings, self.key_setting_name, "") or ""):
            errors.append(
                Error(f"{self.key_setting_name} 미설정 — 암호화 키 필수", obj=self, id="core.E_encrypted_key")
            )
        return errors

    def get_prep_value(self, value: str | None) -> str | None:
        if not value:
            return None
        return self._fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value: str | None, expression: typing.Any, connection: typing.Any) -> str | None:
        if not value:
            return None
        return self._fernet().decrypt(value.encode()).decode()
