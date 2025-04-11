import collections.abc
import contextlib
import typing
import uuid

from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.models import AutoField, UUIDField, expressions, fields
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
