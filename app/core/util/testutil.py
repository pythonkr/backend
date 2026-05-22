def errors_payload(errors: dict | list) -> dict | list:
    """DRF `serializer.errors` / `ValidationError.detail` 을 plain dict / list 로 변환.

    `ErrorDetail` 은 `str` subclass 라 `__eq__` 가 string 만 비교 — code 변경이 dict equality 로 잡히지 않는다.
    본 헬퍼로 `{detail, code}` 평탄화 후 비교하면 message + code 둘 다 catch.
    """

    def _err(e) -> dict:
        return {"detail": str(e), "code": e.code}

    if isinstance(errors, list):
        return [_err(e) for e in errors]
    return {k: [_err(e) for e in v] for k, v in errors.items()}
