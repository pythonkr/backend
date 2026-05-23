class CriticalErrorMessages:
    INVALID_LOGIC = "발생하면 안 되는 오류가 발생했습니다. PyCon 한국 준비 위원회에 문의해주세요.\n{}"


class SignInErrorMessages:
    USER_NOT_SIGNED_IN = "로그인 후 이용해주세요."


class PermissionErrorMessages:
    INVALID_API_KEY = "API Key가 올바르지 않습니다."
    INVALID_OTP_CODE = "OTP 코드가 올바르지 않습니다."
    OTP_REQUIRED = "환불 승인자의 OTP 코드가 필요합니다."


class ProductNotOrderableErrorMessages:
    ALREADY_ORDERED = "이미 결제한 상품입니다. 다시 장바구니에 담아주세요."
    NOT_ORDERABLE_TIME = "{} 상품은 현재 구매하실 수 없습니다."
    SOLDOUT = "{} 상품은 매진되었습니다."
    ALREADY_ORDERED_TOO_MUCH = "{} 상품의 인당 최대 구매 수량 초과로 구매하실 수 없습니다."
    TOO_MUCH_CART_PRODUCT = "{} 상품의 재고 수량을 초과하여 구매하실 수 없습니다. 장바구니에 담은 수량을 확인해주세요."
    PRICE_TOO_HIGH = "결제 금액이 너무 높습니다, 후원 금액 등을 줄여 100만원 미만으로 구매해주세요."
    DONATION_NOT_ALLOWED = "{} 상품은 후원이 불가능한 상품입니다."
    DONATION_PRICE_OUT_OF_RANGE = "{} 상품의 후원 금액이 범위를 벗어났습니다. {}원 이상 {}원 이하로 입력해주세요."


class TagNotOrderableErrorMessages:
    SOLDOUT = "{} 상품군은 매진되었습니다."
    ALREADY_ORDERED_TOO_MUCH_RELATED_PRODUCTS = "{} 상품군의 인당 최대 구매 수량 초과로 구매하실 수 없습니다."


class OptionGroupNotOrderableErrorMessages:
    CUSTOM_RESPONSE_PATTERN_MISMATCH = "옵션의 추가 정보를 올바른 형식으로 입력해주세요."
    OPTION_NOT_MATCH_PRODUCT = "{} 상품의 옵션이 아닌 옵션이 포함되어 있습니다."
    OPTION_NOT_SELECTED = "옵션을 선택해주세요."
    SOLDOUT = "{} 상품의 필수 구매 옵션인 '{}' 옵션이 매진되어 상품을 구매하실 수 없습니다."
    NOT_ENOUGH_OPTION = "{} 상품의 필수 구매 옵션인 '{}' 옵션을 선택해주세요."
    TOO_MUCH_OPTION = "{} 상품의 '{}' 옵션을 너무 많이 선택하셨습니다."


class OptionNotOrderableErrorMessages:
    SOLDOUT = "{} 상품의 '{}' 옵션은 매진되었습니다."
    ALREADY_ORDERED_TOO_MUCH = "{} 상품 '{}' 옵션의 인당 최대 구매 수량 초과로 구매하실 수 없습니다."
    TOO_MUCH_CART_OPTION = "{} 상품의 '{}' 옵션을 너무 많이 선택하셨습니다. 장바구니에 담은 수량을 확인해주세요."


class CartNotOrderableErrorMessages:
    ALREADY_ORDERED = "이미 결제한 장바구니입니다."
    CONTAINS_PAID_PRODUCT = "결제한 상품이 포함되어 있습니다. PyCon 한국 준비 위원회에 문의해주세요."
    EMPTY = "장바구니가 비어있습니다, 먼저 상품을 담아주세요."
    CART_PRICE_TOO_LOW = "장바구니의 금액이 너무 낮습니다. 최소한 1원 이상으로 구매해주세요."
    CART_PRICE_TOO_HIGH = "장바구니의 금액이 너무 높습니다. 일부 상품을 제거하여 100만원 미만으로 구매해주세요."


class NotRefundableErrorMessages:
    ONE_OF_PRODUCT_IS_USED = "주문 중 이미 사용한 상품이 존재합니다. 개별 환불을 진행해주세요."
    ONE_OF_PRODUCT_IS_USED_TRY_AFTER_CHANGING_STATUS = (
        "주문 중 사용한 상품이 존재합니다. 상태를 변경한 후 다시 시도해주세요."
    )
    ONE_OF_PRODUCT_REFUND_TIME_EXPIRED = "주문 중 환불 가능 기간이 지난 상품이 존재합니다. 개별 환불을 진행해주세요."
    PRODUCT_REFUND_TIME_EXPIRED = "상품의 환불 가능 기간이 지났습니다. PyCon 한국 준비 위원회에 문의해주세요."
    PRODUCT_PRICE_IS_ZERO = "환불 가능한 상품이 아닙니다. (환불할 금액이 없습니다.)"
    PRODUCT_STATUS_IS_NOT_PAID = (
        "결제하지 않았거나, 이미 사용했거나 환불한 상품입니다. PyCon 한국 준비 위원회에 문의해주세요."
    )
    ORDER_NOT_REFUNDABLE = "결제 내역 문제로 환불이 불가능한 주문입니다. PyCon 한국 준비 위원회에 문의해주세요."
    ORDER_NOT_REFUNDABLE_STATUS = "환불이 불가능한 주문 상태입니다. PyCon 한국 준비 위원회에 문의해주세요."
    ORDER_REFUNDABLE_PRODUCT_NOT_FOUND = "환불 가능한 상품이 없습니다."
    ORDER_REFUNDABLE_PRICE_NOT_FOUND = "환불 가능한 금액이 없습니다."
    ORDER_REFUND_TARGET_PRICE_IS_MISMATCH = (
        "환불할 금액이 남은 결제 금액과 일치하지 않습니다. PyCon 한국 준비 위원회에 문의해주세요."
    )
    ORDER_IMP_ID_NOT_EXIST = "환불이 불가능한 주문입니다. PyCon 한국 준비 위원회에 문의해주세요."


class OptionGroupNotModifiableErrorMessages:
    ORDER_PRODUCT_OPTION_RELATION_MISMATCH = "해당 옵션을 찾을 수 없습니다."
    CUSTOM_RESPONSE_PATTERN_MISMATCH = "옵션의 추가 정보를 올바른 형식으로 입력해주세요."
    RESPONSE_MODIFIABLE_ENDS_AT = "옵션의 추가 정보 수정 기간이 지났습니다."
    RESPONSE_NOT_MODIFIABLE = "해당 옵션은 수정할 수 없습니다. PyCon 한국 준비 위원회에 문의해주세요."


class PortOneWebhookFailureMessages:
    ORDER_NOT_FOUND = "주문 정보가 존재하지 않습니다."
    PURCHASE_FAILED = "결제에 실패했습니다."
    VIRTUAL_ACCOUNT_NOT_SUPPORTED = "가상계좌 결제는 지원하지 않습니다."
    UNEXPECTED_RETRIEVED_ORDER_STATUS = "예상한 결제 상태가 아닙니다."
    UNEXPECTED_RETRIEVED_ORDER_ID = "결제 ID가 일치하지 않습니다."
    UNEXPECTED_PAID_PRICE = "결제 금액이 일치하지 않습니다."
    UNSUPPORTED_CURRENCY = "지원하지 않는 통화입니다."
    ILLEGAL_STATUS_TRANSITION = "이미 처리된 결제이거나 허용되지 않는 상태 전환입니다."
    CANCELLED_NOT_SUPPORTED = "관리자 콘솔에서 결제 취소된 webhook 의 자동 처리는 아직 지원하지 않습니다."
