from django.core.validators import RegexValidator

HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}){1,2}$",
    message="색상은 #RGB 또는 #RRGGBB 형식의 hex 코드여야 합니다.",
)
