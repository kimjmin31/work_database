from dataclasses import asdict, dataclass, field

from postgrest.exceptions import APIError

from ..utils.time import get_timestamptz
from .base_service import BaseService


@dataclass(kw_only=True)
class OrderItemInfo:
    product_id: str
    quantity: int = 1


@dataclass(kw_only=True)
class OrderInfo:
    p_order_name: str
    p_order_email: str
    p_order_phone: str
    p_receiver_name: str
    p_receiver_phone: str
    p_zipcode: str
    p_address: str
    p_address_sub: str = ""
    p_delivery_memo: str = ""
    p_items: list[OrderItemInfo] = field(default_factory=list)


@dataclass(kw_only=True)
class DeliveryInfo:
    receiver_name: str | None = None
    receiver_phone: str | None = None
    zipcode: str | None = None
    address: str | None = None
    address_sub: str | None = None
    delivery_memo: str | None = None


class OrderService(BaseService):
    # [C] 주문 생성
    #   orders + order_items + total_price 계산을 DB 함수 하나(단일 트랜잭션)로 처리한다.
    #   사용자 ID 는 DB 함수가 auth.uid() 로 직접 확인하므로 넘기지 않는다.
    def order(self, order: OrderInfo):
        if not order.p_items:
            raise ValueError("주문할 상품을 1개 이상 선택해주세요.")
        if any(item.quantity < 1 for item in order.p_items):
            raise ValueError("주문 수량은 1개 이상이어야 합니다.")

        try:
            self.get_user_info()
            if self.get_user_type() != "BUYER":
                raise PermissionError("상품 구매는 일반(BUYER) 계정으로만 가능합니다.")

            response = self.client.rpc(
                "create_order_transaction", asdict(order)
            ).execute()

            if response and response.data:
                return response.data
            else:
                raise RuntimeError("상품 주문에 실패하였습니다.")
        except APIError as e:
            raise self.to_app_error(
                e, "주문 처리 중 서버에 문제가 발생하였습니다."
            ) from e

    # [R] 내 주문 목록 조회 (주문 상품 포함)
    def get_orders(self, include_canceled: bool = False):
        try:
            user = self.get_user_info()
            query = (
                self.get_orders_table()
                .select("*, order_items(*)")
                .eq("user_id", user.id)
            )
            if not include_canceled:
                query = query.is_("deleted_at", "null")

            response = query.order("created_at", desc=True).execute()
            return response.data
        except APIError as e:
            raise self.to_app_error(
                e, "주문 목록 조회 시 문제가 발생하였습니다."
            ) from e

    # [R] 주문 단건 조회 (주문 상품 포함)
    def get_order(self, order_id: str):
        try:
            user = self.get_user_info()
            response = (
                self.get_orders_table()
                .select("*, order_items(*)")
                .eq("id", order_id)
                .eq("user_id", user.id)
                .limit(1)
                .maybe_single()
                .execute()
            )

            if response and response.data:
                return response.data
            else:
                raise LookupError("주문을 찾을 수 없습니다.")
        except APIError as e:
            raise self.to_app_error(e, "주문 조회 시 문제가 발생하였습니다.") from e

    # [U] 배송 정보 수정 (결제 전 READY 상태의 본인 주문만)
    #   금액·상태 컬럼은 DB 컬럼 권한으로 막혀 있어 배송 정보만 수정할 수 있다.
    def update_delivery(self, order_id: str, info: DeliveryInfo):
        values = {k: v for k, v in asdict(info).items() if v is not None}
        if not values:
            raise ValueError("수정할 항목이 없습니다.")

        try:
            user = self.get_user_info()
            values["modified_at"] = get_timestamptz()
            response = (
                self.get_orders_table()
                .update(values)
                .eq("id", order_id)
                .eq("user_id", user.id)
                .eq("order_status", "READY")
                .is_("deleted_at", "null")
                .execute()
            )

            if response and response.data:
                return response.data[0]
            else:
                raise LookupError(
                    "수정 가능한 주문이 없습니다. (결제 전 본인 주문만 수정 가능)"
                )
        except APIError as e:
            raise self.to_app_error(
                e, "배송 정보 수정 시 문제가 발생하였습니다."
            ) from e

    # [D] 주문 취소 (soft delete)
    #   orders 상태 변경 + order_items 삭제 표시를 DB 함수 하나(단일 트랜잭션)로 처리한다.
    def cancel(self, order_id: str):
        try:
            self.get_user_info()
            response = self.client.rpc(
                "cancel_order", {"p_order_id": order_id}
            ).execute()

            if response and response.data:
                return response.data
            else:
                raise RuntimeError("주문 취소에 실패하였습니다.")
        except APIError as e:
            raise self.to_app_error(
                e, "주문 취소 중 서버에 문제가 발생하였습니다."
            ) from e

    # 내 주문 건수 (트랜잭션 검증용)
    def count_orders(self) -> dict[str, int]:
        user = self.get_user_info()
        orders = (
            self.get_orders_table()
            .select("id", count="exact")
            .eq("user_id", user.id)
            .execute()
        )
        # order_items 는 RLS 로 본인 주문의 상품만 조회되므로 별도 필터가 필요 없다.
        items = self.get_order_items_table().select("id", count="exact").execute()
        return {"orders": orders.count or 0, "order_items": items.count or 0}
