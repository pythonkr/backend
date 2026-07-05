import secrets
import string

MERGE_SOURCE_SESSION_KEY = "account_merge_source_user_id"
MERGE_MESSAGES = {
    "wrong_account_or_password": {
        "ko": "이메일(또는 아이디)이나 비밀번호가 올바르지 않습니다.",
        "en": "Your email/username or password is incorrect.",
    },
    "target_no_verified_email": {
        "ko": "남길 계정에 인증된 이메일이 필요합니다. 이메일을 추가하고 인증한 뒤 다시 시도해 주세요.",
        "en": "The account you keep needs a verified email. Add and verify an email, then try again.",
    },
    "target_unverified_email": {
        "ko": "남길 계정에 인증되지 않은 이메일이 있습니다. 인증을 완료하거나 해당 이메일을 삭제한 뒤 다시 시도해 주세요.",
        "en": "The account you keep has an unverified email. Verify it or delete that email, then try again.",
    },
    "source_unverified_email": {
        "ko": "합칠 계정에 인증되지 않은 이메일이 있습니다. 해당 계정으로 로그인해 인증을 완료하거나 삭제한 뒤 다시 시도해 주세요.",
        "en": (
            "The account to merge has an unverified email. "
            "Sign in to that account to verify or delete it, then try again."
        ),
    },
    "same_account": {
        "ko": "같은 계정끼리는 병합할 수 없습니다.",
        "en": "You can't merge an account with itself.",
    },
    "target_already_merged": {
        "ko": "남길 계정이 이미 다른 계정에 병합되어 있습니다.",
        "en": "The account you keep has already been merged into another account.",
    },
    "source_already_merged": {
        "ko": "합칠 계정이 이미 다른 계정에 병합되어 있습니다.",
        "en": "The account to merge has already been merged into another account.",
    },
    "already_reverted": {
        "ko": "이미 되돌린 병합입니다.",
        "en": "This merge has already been reverted.",
    },
    "later_merge_first": {
        "ko": "이 병합의 남긴 계정이 이후 다른 계정에 다시 병합되었습니다. 나중 병합부터 되돌려 주세요.",
        "en": "The kept account was later merged again. Revert the more recent merge first.",
    },
    "no_source": {
        "ko": "병합할 계정 정보를 찾을 수 없습니다. 다시 시도해 주세요.",
        "en": "We couldn't find the account to merge. Please try again.",
    },
}
EMAIL_MESSAGES = {
    "verification_sent": {
        "ko": "확인 이메일을 보냈습니다. 메일함을 확인해 주세요.",
        "en": "A verification email has been sent. Please check your inbox.",
    },
    "resent": {
        "ko": "확인 이메일을 다시 보냈습니다.",
        "en": "The verification email has been resent.",
    },
    "verified": {
        "ko": "이메일이 인증되었습니다.",
        "en": "Your email has been verified.",
    },
    "already_verified": {
        "ko": "이미 인증된 이메일입니다.",
        "en": "This email is already verified.",
    },
    "invalid_link": {
        "ko": "확인 링크가 유효하지 않거나 만료되었습니다.",
        "en": "The verification link is invalid or has expired.",
    },
    "deleted": {
        "ko": "이메일을 삭제했습니다.",
        "en": "The email has been removed.",
    },
    "cannot_delete": {
        "ko": "이 이메일은 삭제할 수 없습니다.",
        "en": "This email can't be removed.",
    },
    "primary_set": {
        "ko": "대표 이메일을 변경했습니다.",
        "en": "Your primary email has been updated.",
    },
    "cannot_set_primary": {
        "ko": "인증된 이메일만 대표로 지정할 수 있습니다.",
        "en": "Only a verified email can be set as your primary email.",
    },
    "add_failed": {
        "ko": "이 이메일은 추가할 수 없습니다. 형식이 올바르지 않거나 이미 사용 중일 수 있습니다.",
        "en": "This email can't be added. It may be invalid or already in use.",
    },
    "not_found": {
        "ko": "이메일을 찾을 수 없습니다.",
        "en": "Email not found.",
    },
}
PASSWORD_MESSAGES = {
    "changed": {
        "ko": "비밀번호를 변경했습니다.",
        "en": "Your password has been changed.",
    },
    "reset_done": {
        "ko": "비밀번호를 재설정했습니다. 이제 새 비밀번호로 로그인할 수 있습니다.",
        "en": "Your password has been reset. You can now sign in with your new password.",
    },
}


def generate_random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return "".join(secrets.choice(alphabet) for _ in range(length))
