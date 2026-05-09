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


def query_grouper(qs: Q, chunk_len: int) -> Generator[Q, Any, None]:
    """
    - iter_smart_chunks는 테이블의 모든 row에 대해 chunk_len만큼 loop를 돌면서 QuerySet을 반환하기에, 빈 QuerySet이 반환될 수 있고,
    - grouper는 QuerySet을 수행하여 결과를 메모리에 올려둔 후 결과를 chunk_len만큼씩 반환하기에, 메모리 사용량이 비교적 높을 수 있습니다.
      이에, created_at 기준으로 chunk_len만큼씩 QuerySet을 반환하는 query_grouper를 추가합니다.
    """
    qs = qs.order_by("created_at")
    curr, end = 0, qs.aggregate(models.Max("id"))["created_at__max"] or 0
    while curr < end:
        chunk = qs.filter(id__gt=curr)[:chunk_len]
        yield chunk
        curr = chunk.aggregate(models.Max("id"))["created_at__max"]
