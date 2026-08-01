import pytest
from core.util.fileutil import read_uploaded_csv
from rest_framework import exceptions

_CSV = "name,phone\n홍길동,010-1234-5678\n"


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp949"])
def test_read_uploaded_csv_reads_supported_encodings(encoding):
    df = read_uploaded_csv(_CSV.encode(encoding))
    # utf-8-sig 로 먼저 디코딩하므로 BOM 이 첫 컬럼명에 남지 않는다.
    assert list(df.columns) == ["name", "phone"]
    assert df.iloc[0]["name"] == "홍길동"


def test_read_uploaded_csv_rejects_unsupported_encoding():
    # Excel 의 "유니코드 텍스트"(UTF-16) 저장 — UTF-8/CP949 둘 다 실패.
    with pytest.raises(exceptions.ValidationError) as e:
        read_uploaded_csv(_CSV.encode("utf-16"))
    assert "csv_file" in e.value.detail


def test_read_uploaded_csv_rejects_malformed_csv():
    with pytest.raises(exceptions.ValidationError) as e:
        read_uploaded_csv(b"a,b,c\n1,2,3\n4,5,6,7,8\n")
    assert "csv_file" in e.value.detail


def test_read_uploaded_csv_rejects_empty_file():
    with pytest.raises(exceptions.ValidationError) as e:
        read_uploaded_csv(b"")
    assert "csv_file" in e.value.detail


def test_read_uploaded_csv_reports_errors_under_given_field():
    with pytest.raises(exceptions.ValidationError) as e:
        read_uploaded_csv(b"", field="attachment")
    assert "attachment" in e.value.detail
