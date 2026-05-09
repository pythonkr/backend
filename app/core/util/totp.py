from base64 import b32encode
from dataclasses import dataclass
from hmac import new as hmac_new
from struct import pack, unpack
from time import time
from typing import Literal
from urllib.parse import quote, urlencode

ALLOWED_DIGESTS = {"sha1", "sha256", "sha512"}


@dataclass(frozen=True)
class TOTPInfo:
    key: bytes
    time_step: int = 30
    digits: int = 6
    digest: Literal["sha1", "sha256", "sha512"] = "sha1"
    window: int = 1

    def __post_init__(self) -> None:
        if self.digest not in ALLOWED_DIGESTS:
            raise ValueError(f"Unsupported digest algorithm: {self.digest}")
        if self.digest != "sha1":
            raise Warning(f"Using {self.digest} is not recommended as Google Authenticator does not support it.")
        if self.time_step != 30:
            raise Warning(f"Using {self.time_step} is not recommended as Google Authenticator does not support it.")

    def get_hotp(self, counter: int) -> str:
        mac = hmac_new(self.key, pack(">Q", counter), self.digest).digest()
        offset = mac[-1] & 0x0F
        binary = unpack(">L", mac[offset : offset + 4])[0] & 0x7FFFFFFF  # noqa: E203
        return str(binary)[-self.digits :].zfill(self.digits)  # noqa: E203

    def get_totp(self, current_time: float | None = None) -> tuple[str, int]:
        counter = int((current_time or time()) / self.time_step)
        leftover_sec = self.time_step - int((current_time or time()) % self.time_step)
        return self.get_hotp(counter=counter), leftover_sec

    def get_allowed_totps(self, current_time: float | None = None) -> list[str]:
        base_counter = int((current_time or time()) / self.time_step)
        return [self.get_hotp(counter=counter) for counter in range(base_counter - self.window, base_counter + 1)]

    def check(self, totp_input: str) -> bool:
        return totp_input.isdigit() and totp_input in self.get_allowed_totps()

    def get_otpauth_uri(self, issuer: str, username: str) -> str:
        encoded_data: str = urlencode(
            query={
                "secret": b32encode(self.key).decode("utf-8"),
                "issuer": issuer,
                "algorithm": self.digest.upper(),
                "digits": self.digits,
                "period": self.time_step,
            }
        )
        return f"otpauth://totp/{quote(string=issuer)}:{quote(string=username)}?{encoded_data}"
