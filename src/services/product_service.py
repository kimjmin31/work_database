from dataclasses import asdict, dataclass

from postgrest.exceptions import APIError

from ..utils.time import get_timestamptz
from .base_service import BaseService


@dataclass(kw_only=True)
class ProductInfo:
    name: str | None = None
    description: str | None = None
    price: int | None = None


class ProductService(BaseService):
    # [C] 상품 등록 (SELLER 전용)
    def add(self, info: ProductInfo):
        if not info.name:
            raise ValueError("상품명은 필수 입력값입니다.")
        if info.price is not None and info.price < 0:
            raise ValueError("가격은 0원 이상이어야 합니다.")

        try:
            if self.get_user_type() != "SELLER":
                raise PermissionError("상품 등록 권한이 없습니다. (판매자 전용)")

            values = {k: v for k, v in asdict(info).items() if v is not None}
            values["seller_id"] = self.get_user_info().id
            response = self.get_products_table().insert(values).execute()

            if response and response.data:
                return response.data[0]
            else:
                raise RuntimeError("상품 등록에 실패하였습니다.")
        except APIError as e:
            raise self.to_app_error(e, "상품 등록 시 문제가 발생하였습니다.") from e

    # [R] 상품 목록 검색
    def search(
        self,
        keyword: str = "",
        seller_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        try:
            query = self.get_products_table().select("*")

            if seller_id:
                query = query.eq("seller_id", seller_id)

            keyword = keyword.strip()
            if keyword:
                query = query.or_(
                    f"name.ilike.%{keyword}%,description.ilike.%{keyword}%"
                )

            response = (
                query.is_("deleted_at", "null")
                .order("created_at", desc=True)
                .range(offset * limit, offset * limit + limit - 1)
                .execute()
            )

            return response.data
        except APIError as e:
            raise self.to_app_error(e, "상품 검색 시 문제가 발생하였습니다.") from e

    # [R] 상품 단건 조회
    def get(self, product_id: str):
        try:
            response = (
                self.get_products_table()
                .select("*")
                .eq("id", product_id)
                .is_("deleted_at", "null")
                .limit(1)
                .maybe_single()
                .execute()
            )

            if response and response.data:
                return response.data
            else:
                raise LookupError("상품을 찾을 수 없습니다.")
        except APIError as e:
            raise self.to_app_error(e, "상품 조회 시 문제가 발생하였습니다.") from e

    # [U] 상품 수정 (본인 상품만)
    def update(self, product_id: str, info: ProductInfo):
        values = {k: v for k, v in asdict(info).items() if v is not None}
        if not values:
            raise ValueError("수정할 항목이 없습니다.")
        if info.price is not None and info.price < 0:
            raise ValueError("가격은 0원 이상이어야 합니다.")

        try:
            user = self.get_user_info()
            values["modified_at"] = get_timestamptz()
            response = (
                self.get_products_table()
                .update(values)
                .eq("seller_id", user.id)
                .eq("id", product_id)
                .is_("deleted_at", "null")
                .execute()
            )

            if response and response.data:
                return response.data[0]
            else:
                raise LookupError("수정할 상품이 없거나 본인 상품이 아닙니다.")
        except APIError as e:
            raise self.to_app_error(e, "상품 수정 시 문제가 발생하였습니다.") from e

    # [D] 상품 삭제 (soft delete, 본인 상품만)
    #   order_items 가 products 를 FK 로 참조하므로 물리 삭제 대신 deleted_at 을 기록한다.
    def delete(self, product_id: str):
        try:
            user = self.get_user_info()
            now = get_timestamptz()
            response = (
                self.get_products_table()
                .update({"deleted_at": now, "modified_at": now})
                .eq("seller_id", user.id)
                .eq("id", product_id)
                .is_("deleted_at", "null")
                .execute()
            )

            if response and response.data:
                return response.data[0]
            else:
                raise LookupError("삭제할 상품이 없거나 본인 상품이 아닙니다.")
        except APIError as e:
            raise self.to_app_error(e, "상품 삭제 시 문제가 발생하였습니다.") from e
