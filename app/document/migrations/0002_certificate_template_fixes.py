from django.db import migrations

# 범-CJK 컬렉션(Noto Sans CJK)은 WeasyPrint 의 폰트 서브셋에만 문서당 ~13초가 걸려 gunicorn timeout 을 넘겼다.
# 한국어 전용 나눔바른고딕은 ~1.2초. Noto 는 나눔에 없는 글자의 폴백으로만 남긴다.
OLD_FONT_STACK = 'font-family: "Noto Sans CJK KR", "Noto Sans KR", "Apple SD Gothic Neo", sans-serif;'
NEW_FONT_STACK = (
    'font-family: "NanumBarunGothic", "NanumGothic", "Noto Sans CJK KR", "Apple SD Gothic Neo", sans-serif;'
)

# 라벨이 박스 하단 테두리에 걸쳐 있어(bottom:0 + translate 50%) 글자가 잘렸다.
# 박스를 세로로 늘려 라벨을 QR 아래에 두고, QR 이미지의 quiet zone(30mm 기준 2.26mm) 안쪽으로만 1mm 끌어올린다.
# 검은 모듈을 가리지 않으므로 스캔 여유가 그대로다. z-index 가 없으면 WeasyPrint 가 QR 이미지를 라벨 위에 그린다.
OLD_QR_CSS = """    .qr {
      height: 32mm;
      width: 32mm;
      position: absolute;
      display: flex;
      align-items: center;
      justify-content: center;
      right: 0;
      top: 0;
      border: 1px solid #bdbdbd;
      border-radius: 2mm;
      text-align: center;
    }

    .qr img {
      width: 30mm;
      height: 30mm;
    }

    .qr .label {
      position: absolute;
      left: 50%;
      bottom: 0;
      padding: 0 2mm;
      transform: translate(-50%, 50%);
      background: #fff;
      font-size: 8pt;
      color: #555;
      white-space: nowrap;
    }"""

NEW_QR_CSS = """    .qr {
      height: 35mm;
      width: 32mm;
      position: absolute;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      right: 0;
      top: 0;
      border: 1px solid #bdbdbd;
      border-radius: 2mm;
      text-align: center;
    }

    .qr img {
      width: 30mm;
      height: 30mm;
    }

    .qr .label {
      position: relative;
      z-index: 1;
      margin-top: -1mm;
      font-size: 7pt;
      color: #555;
      white-space: nowrap;
    }"""

REPLACEMENTS = ((OLD_FONT_STACK, NEW_FONT_STACK), (OLD_QR_CSS, NEW_QR_CSS))


def _apply(apps, pairs) -> None:
    DocumentTemplate = apps.get_model("document", "DocumentTemplate")
    for template in DocumentTemplate.objects.filter(deleted_at__isnull=True):
        body = template.body
        # 문자열이 정확히 맞는 것만 — 어드민이 본문을 손댔다면 그 부분은 건드리지 않는다.
        for old, new in pairs:
            body = body.replace(old, new)
        if body != template.body:
            template.body = body
            template.save(update_fields=["body", "updated_at"])


def forwards(apps, schema_editor):
    _apply(apps, REPLACEMENTS)


def backwards(apps, schema_editor):
    _apply(apps, tuple((new, old) for old, new in REPLACEMENTS))


class Migration(migrations.Migration):
    dependencies = [
        ("document", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
