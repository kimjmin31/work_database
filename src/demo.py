"""
README 캡처용 CRUD / 트랜잭션 / RLS 시연 스크립트

실행 (프로젝트 루트에서)
    uv run python -m src.demo            # 전체
    uv run python -m src.demo user       # 회원 CRUD
    uv run python -m src.demo product    # 상품 CRUD
    uv run python -m src.demo order      # 주문 CRUD
    uv run python -m src.demo tx         # 트랜잭션 COMMIT / ROLLBACK 검증
    uv run python -m src.demo rls        # RLS 권한 정책 / 예외 처리 검증

사전 준비
    Supabase 대시보드 > Authentication > Sign In / Providers > Email 에서
    "Confirm email" 을 끄면 테스트 계정으로 바로 로그인할 수 있다.
"""

import json
import os
import sys
from collections.abc import Callable

from postgrest.exceptions import APIError

from src.main import client
from src.services.order_service import (
    DeliveryInfo,
    OrderInfo,
    OrderItemInfo,
    OrderService,
)
from src.services.product_service import ProductInfo, ProductService
from src.services.user_service import Account, AccountInfo, UserService

PASSWORD = os.getenv("DEMO_PASSWORD", "password1234")
BUYER = Account(
    email=os.getenv("DEMO_BUYER_EMAIL", "user01@test.com"), password=PASSWORD
)
SELLER = Account(
    email=os.getenv("DEMO_SELLER_EMAIL", "user02@test.com"), password=PASSWORD
)
WITHDRAW = Account(
    email=os.getenv("DEMO_WITHDRAW_EMAIL", "user03@test.com"), password=PASSWORD
)

user_service = UserService(client)
product_service = ProductService(client)
order_service = OrderService(client)

# 섹션 간에 공유하는 값 (예: 삭제된 상품 ID)
state: dict[str, str] = {}


# ----------------------------------------------------------------------
# 출력 헬퍼
# ----------------------------------------------------------------------
def section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def step(label: str, data=None):
    print(f"\n▶ {label}")
    if data is not None:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def expect_error(label: str, fn: Callable):
    print(f"\n▶ {label}")
    try:
        result = fn()
        print("  ⚠️  예외가 발생하지 않았습니다:", result)
    except (APIError, PermissionError, ValueError, LookupError, RuntimeError) as e:
        name = type(e).__name__
        message = e.message if isinstance(e, APIError) else str(e)
        code = f" [{e.code}]" if isinstance(e, APIError) else ""
        print(f"  ✅ 차단됨 → {name}{code}: {message}")


def pick(row: dict, *keys: str) -> dict:
    return {k: row.get(k) for k in keys}


def login_as(account: Account, details: AccountInfo):
    """가입(이미 있으면 건너뜀) → 로그인 → 상세 정보가 없으면 등록"""
    try:
        user_service.sign_up(account)
    except ValueError:
        pass
    user_service.login(account)
    if "type" not in user_service.get_details():
        user_service.create_details(details)


SELLER_DETAILS = AccountInfo(
    type="SELLER",
    cellphone="010-0300-0300",
    zipcode="04000",
    address="서울시 판매구",
    address_sub="2층",
)
BUYER_DETAILS = AccountInfo(
    type="BUYER",
    cellphone="010-0000-0000",
    zipcode="01000",
    address="서울시 구매구",
    address_sub="101호",
)


# ----------------------------------------------------------------------
# 1. 회원 CRUD
# ----------------------------------------------------------------------
def demo_user():
    section("회원 CRUD  (auth.users + public.user_details)")

    # [C] 회원가입 + 상세 정보 등록
    try:
        user = user_service.sign_up(WITHDRAW)
        step("[CREATE] 회원가입 (auth.users)", {"id": user.id, "email": user.email})
    except ValueError as e:
        step(f"[CREATE] 회원가입 → 이미 가입된 계정이므로 로그인으로 진행 ({e})")

    user_service.login(WITHDRAW)
    details = user_service.get_details()
    if "type" in details:
        step("[CREATE] 상세 정보가 이미 존재하여 등록 생략", details)
    else:
        created = user_service.create_details(
            AccountInfo(
                type="BUYER",
                cellphone="010-3333-3333",
                zipcode="03000",
                address="서울시 테스트구",
            )
        )
        step("[CREATE] 회원 상세 정보 등록 (user_details)", created)

    # [R]
    step("[READ] 회원 정보 조회", user_service.get_details())

    # [U]
    updated = user_service.update_details(
        AccountInfo(
            cellphone="010-9999-9999", address="서울시 변경구", address_sub="303호"
        )
    )
    step(
        "[UPDATE] 휴대폰·주소 수정 → modified_at 기록",
        pick(updated, "cellphone", "address", "address_sub", "modified_at"),
    )

    # [D]
    deleted = user_service.withdraw()
    step(
        "[DELETE] 회원 탈퇴 (soft delete → deleted_at 기록)",
        pick(deleted, "id", "deleted_at"),
    )
    step("[READ] 탈퇴 후 조회 → 상세 정보 없음", user_service.get_details())

    user_service.logout()


# ----------------------------------------------------------------------
# 2. 상품 CRUD
# ----------------------------------------------------------------------
def demo_product():
    section("상품 CRUD  (public.products)  — 판매자 계정")
    login_as(SELLER, SELLER_DETAILS)

    # [C]
    p1 = product_service.add(
        ProductInfo(
            name="스파르타 JS 교안", description="JS 기초 학습 가능", price=15000
        )
    )
    p2 = product_service.add(
        ProductInfo(
            name="스파르타 파이썬 교안",
            description="파이썬 기초 학습 가능",
            price=20000,
        )
    )
    p3 = product_service.add(
        ProductInfo(name="삭제 테스트 상품", description="곧 삭제됩니다", price=1000)
    )
    step(
        "[CREATE] 상품 3개 등록",
        [pick(p, "id", "name", "price", "seller_id") for p in (p1, p2, p3)],
    )

    # [R]
    step(
        "[READ] 전체 상품 조회",
        [pick(p, "name", "price") for p in product_service.search()],
    )
    step(
        "[READ] 키워드 '파이썬' 검색",
        [pick(p, "name", "description") for p in product_service.search("파이썬")],
    )

    # [U]
    before = product_service.get(p2["id"])
    after = product_service.update(
        p2["id"], ProductInfo(name="스파르타 파이썬 교안 (개정판)", price=25000)
    )
    step(
        "[UPDATE] 상품명·가격 수정 (before → after)",
        {
            "before": pick(before, "name", "price", "modified_at"),
            "after": pick(after, "name", "price", "modified_at"),
        },
    )

    # [D]
    deleted = product_service.delete(p3["id"])
    state["deleted_product_id"] = p3["id"]
    step(
        "[DELETE] 상품 삭제 (soft delete → deleted_at 기록)",
        pick(deleted, "id", "name", "deleted_at"),
    )
    step(
        "[READ] 삭제 후 전체 조회 → 삭제 상품 제외",
        [pick(p, "name", "price") for p in product_service.search()],
    )
    expect_error("[READ] 삭제된 상품 단건 조회", lambda: product_service.get(p3["id"]))

    user_service.logout()


# ----------------------------------------------------------------------
# 3. 주문 CRUD
# ----------------------------------------------------------------------
def demo_order():
    section("주문 CRUD  (public.orders + public.order_items)  — 구매자 계정")
    login_as(BUYER, BUYER_DETAILS)

    products = product_service.search(limit=2)
    if len(products) < 2:
        raise SystemExit(
            "판매 중인 상품이 2개 이상 필요합니다. 먼저 `uv run python -m src.demo product` 를 실행하세요."
        )

    me = user_service.get_details()

    def new_order(memo: str) -> OrderInfo:
        return OrderInfo(
            p_order_name="김철수",
            p_order_email=me["email"],
            p_order_phone=me["cellphone"],
            p_receiver_name="이영희",
            p_receiver_phone="010-1234-5678",
            p_zipcode="03200",
            p_address="받는사람 주소",
            p_address_sub="받는사람 상세 주소",
            p_delivery_memo=memo,
            p_items=[
                OrderItemInfo(product_id=products[0]["id"], quantity=1),
                OrderItemInfo(product_id=products[1]["id"], quantity=2),
            ],
        )

    # [C]
    created = order_service.order(new_order("문앞에 두세요."))
    step(
        "[CREATE] 주문 생성 (orders 1건 + order_items 2건, 단일 트랜잭션)",
        {
            "주문 상품": [f"{p['name']} {p['price']:,}원" for p in products],
            "결과": created,
        },
    )

    # [R]
    order = order_service.get_order(created["order_id"])
    step(
        "[READ] 주문 상세 조회 (주문 + 주문 상품)",
        {
            **pick(
                order,
                "order_no",
                "order_status",
                "receiver_name",
                "address",
                "total_price",
            ),
            "order_items": [
                pick(i, "item_name", "price", "quantity") for i in order["order_items"]
            ],
        },
    )

    # [U]
    updated = order_service.update_delivery(
        created["order_id"],
        DeliveryInfo(
            address="변경된 배송지 주소",
            address_sub="502호",
            delivery_memo="경비실에 맡겨주세요.",
        ),
    )
    step(
        "[UPDATE] 배송 정보 수정 (before → after)",
        {
            "before": pick(order, "address", "address_sub", "delivery_memo"),
            "after": pick(
                updated, "address", "address_sub", "delivery_memo", "modified_at"
            ),
        },
    )

    # [D]
    canceled = order_service.cancel(created["order_id"])
    step(
        "[DELETE] 주문 취소 (orders + order_items soft delete, 단일 트랜잭션)", canceled
    )
    step(
        "[READ] 취소 포함 전체 주문 조회",
        [
            pick(o, "order_no", "order_status", "deleted_at")
            for o in order_service.get_orders(include_canceled=True)
        ],
    )
    expect_error(
        "[DELETE] 이미 취소된 주문 재취소",
        lambda: order_service.cancel(created["order_id"]),
    )

    user_service.logout()


# ----------------------------------------------------------------------
# 4. 트랜잭션 COMMIT / ROLLBACK
# ----------------------------------------------------------------------
def demo_transaction():
    section("트랜잭션 검증  (create_order_transaction)")
    login_as(BUYER, BUYER_DETAILS)

    products = product_service.search(limit=1)
    if not products:
        raise SystemExit(
            "판매 중인 상품이 필요합니다. 먼저 `uv run python -m src.demo product` 를 실행하세요."
        )
    me = user_service.get_details()

    def order_with(items: list[OrderItemInfo], memo: str):
        return order_service.order(
            OrderInfo(
                p_order_name="김철수",
                p_order_email=me["email"],
                p_order_phone=me["cellphone"],
                p_receiver_name="이영희",
                p_receiver_phone="010-1234-5678",
                p_zipcode="03200",
                p_address="받는사람 주소",
                p_delivery_memo=memo,
                p_items=items,
            )
        )

    step("[0] 시작 시점 내 주문 건수", order_service.count_orders())

    # 성공 → COMMIT
    result = order_with(
        [OrderItemInfo(product_id=products[0]["id"], quantity=1)],
        "트랜잭션 성공 테스트",
    )
    step("[1] 성공 시나리오 → COMMIT", result)
    step("    주문 건수 (orders +1, order_items +1)", order_service.count_orders())

    # 실패 → ROLLBACK
    invalid_id = state.get("deleted_product_id", "00000000-0000-0000-0000-000000000000")
    print(
        "\n▶ [2] 실패 시나리오: 1번째 상품은 정상, 2번째 상품은 삭제된(존재하지 않는) 상품"
    )
    print(f"    - 정상 상품 : {products[0]['id']}")
    print(f"    - 잘못된 상품: {invalid_id}")
    print("    함수 안에서 orders 1건, order_items 1건이 먼저 INSERT 된 뒤 예외 발생")
    expect_error(
        "    주문 요청",
        lambda: order_with(
            [
                OrderItemInfo(product_id=products[0]["id"], quantity=1),
                OrderItemInfo(product_id=invalid_id, quantity=1),
            ],
            "트랜잭션 실패 테스트",
        ),
    )
    step(
        "    주문 건수 → [1] 과 동일 (먼저 INSERT 된 행까지 모두 ROLLBACK)",
        order_service.count_orders(),
    )

    rolled_back = [
        o
        for o in order_service.get_orders(include_canceled=True)
        if o["delivery_memo"] == "트랜잭션 실패 테스트"
    ]
    step("    '트랜잭션 실패 테스트' 주문 검색 결과", rolled_back)

    user_service.logout()


# ----------------------------------------------------------------------
# 5. RLS 권한 정책 / 예외 처리
# ----------------------------------------------------------------------
def demo_rls():
    section("RLS 권한 정책 / 예외 처리")

    # 비로그인
    user_service.logout()
    step(
        "[비로그인] 판매 중인 상품 조회 → 허용",
        [pick(p, "name", "price") for p in product_service.search(limit=3)],
    )
    expect_error("[비로그인] 내 주문 조회", lambda: order_service.get_orders())
    expect_error(
        "[비로그인] products 테이블 직접 INSERT (RLS)",
        lambda: (
            client.table("products")
            .insert(
                {
                    "name": "몰래 등록",
                    "price": 1,
                    "seller_id": "00000000-0000-0000-0000-000000000000",
                }
            )
            .execute()
        ),
    )

    # 구매자
    login_as(BUYER, BUYER_DETAILS)
    buyer_id = user_service.get_user_info().id
    expect_error(
        "[구매자] 상품 등록 (서비스 권한 검사)",
        lambda: product_service.add(ProductInfo(name="구매자 상품", price=100)),
    )
    expect_error(
        "[구매자] products 테이블 직접 INSERT (RLS: SELLER 만 허용)",
        lambda: (
            client.table("products")
            .insert({"name": "구매자 상품", "price": 100, "seller_id": buyer_id})
            .execute()
        ),
    )
    expect_error(
        "[구매자] orders 테이블 직접 INSERT (RLS: 함수로만 생성 가능)",
        lambda: (
            client.table("orders")
            .insert(
                {
                    "user_id": buyer_id,
                    "order_name": "a",
                    "order_email": "a",
                    "order_phone": "a",
                    "receiver_name": "a",
                    "receiver_phone": "a",
                    "zipcode": "a",
                    "address": "a",
                    "total_price": 0,
                }
            )
            .execute()
        ),
    )
    expect_error(
        "[구매자] 주문 금액(total_price) 직접 수정 (컬럼 권한)",
        lambda: (
            client.table("orders")
            .update({"total_price": 0})
            .eq("user_id", buyer_id)
            .execute()
        ),
    )
    others = (
        client.table("products")
        .select("id, seller_id")
        .neq("seller_id", buyer_id)
        .limit(1)
        .execute()
        .data
    )
    if others:
        expect_error(
            "[구매자] 다른 사람 상품 수정",
            lambda: product_service.update(others[0]["id"], ProductInfo(price=0)),
        )
    expect_error(
        "[구매자] 가격 음수로 수정 (입력값 검증)",
        lambda: product_service.update(
            others[0]["id"] if others else "x", ProductInfo(price=-1)
        ),
    )
    expect_error(
        "[구매자] 빈 주문 (입력값 검증)",
        lambda: order_service.order(
            OrderInfo(
                p_order_name="a",
                p_order_email="a",
                p_order_phone="a",
                p_receiver_name="a",
                p_receiver_phone="a",
                p_zipcode="a",
                p_address="a",
                p_items=[],
            )
        ),
    )
    expect_error(
        "[구매자] 잘못된 ID 형식으로 주문 조회",
        lambda: order_service.get_order("not-a-uuid"),
    )
    user_service.logout()

    # 판매자
    login_as(SELLER, SELLER_DETAILS)
    expect_error(
        "[판매자] 주문 함수 직접 호출 (DB 함수 내부 권한 검사)",
        lambda: client.rpc(
            "create_order_transaction",
            {
                "p_order_name": "a",
                "p_order_email": "a",
                "p_order_phone": "a",
                "p_receiver_name": "a",
                "p_receiver_phone": "a",
                "p_zipcode": "a",
                "p_address": "a",
                "p_address_sub": "",
                "p_delivery_memo": "",
                "p_items": [
                    {
                        "product_id": "00000000-0000-0000-0000-000000000000",
                        "quantity": 1,
                    }
                ],
            },
        ).execute(),
    )
    step(
        "[판매자] 다른 사람 주문 조회 → RLS 로 0건",
        client.table("orders").select("id").execute().data,
    )
    user_service.logout()


SECTIONS = {
    "user": demo_user,
    "product": demo_product,
    "order": demo_order,
    "tx": demo_transaction,
    "rls": demo_rls,
}

if __name__ == "__main__":
    targets = sys.argv[1:] or list(SECTIONS)
    for name in targets:
        if name not in SECTIONS:
            raise SystemExit(
                f"알 수 없는 섹션: {name}  (사용 가능: {', '.join(SECTIONS)})"
            )
        SECTIONS[name]()
