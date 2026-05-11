from collections.abc import Generator, Iterable, Iterator
from itertools import islice
from typing import Any, TypeVar

from django.db import models

T = TypeVar("T")
Q = TypeVar("Q", bound=models.QuerySet[models.Model])


def grouper(iterable: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:
    iterator = iter(iterable)
    while True:
        if not (elements := tuple(islice(iterator, n))):
            return
        yield elements


def query_grouper(qs: Q, chunk_len: int) -> Generator[list, Any, None]:
    """`(created_at, id)` 복합 커서로 chunk 단위 list 를 yield. 동일 created_at 인 row 도 누락 없이 처리."""
    qs = qs.order_by("created_at", "id")
    last_created_at, last_id = None, None
    while True:
        chunk_qs = qs
        if last_created_at is not None:
            chunk_qs = qs.filter(
                models.Q(created_at__gt=last_created_at) | models.Q(created_at=last_created_at, id__gt=last_id),
            )
        if not (chunk := list(chunk_qs[:chunk_len])):
            return
        yield chunk
        last_created_at, last_id = chunk[-1].created_at, chunk[-1].id
