import io

import pandas
from rest_framework import exceptions

# 한국어 Windows Excel 의 "CSV (쉼표로 분리)" 저장은 CP949 이므로 UTF-8 만으로는 읽을 수 없다.
# 순서 중요 — UTF-8 을 먼저 시도해야 CP949 가 UTF-8 본문을 깨진 글자로 잘못 읽는 것을 막는다.
CSV_ENCODINGS = ("utf-8-sig", "cp949")


def read_uploaded_csv(raw: bytes, *, field: str = "csv_file") -> pandas.DataFrame:
    """업로드된 CSV 를 DataFrame 으로 파싱. 인코딩·파싱 실패를 500 대신 400 으로 돌려준다."""
    for encoding in CSV_ENCODINGS:
        try:
            decoded = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise exceptions.ValidationError(
            {field: "CSV 파일의 문자 인코딩을 인식할 수 없습니다. UTF-8 또는 CP949 로 저장해주세요."}
        )

    try:
        return pandas.read_csv(io.StringIO(decoded))
    except (pandas.errors.ParserError, pandas.errors.EmptyDataError) as e:
        raise exceptions.ValidationError({field: f"CSV 파일을 읽을 수 없습니다: {e}"}) from e
