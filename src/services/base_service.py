from postgrest import SyncRequestBuilder
from postgrest.exceptions import APIError
from supabase import Client
from supabase._sync.auth_client import SyncSupabaseAuthClient


class BaseService:
    def __init__(self, client: Client):
        self.client = client

    # ------------------------------------------------------------------
    # 인증
    # ------------------------------------------------------------------
    def get_auth(self) -> SyncSupabaseAuthClient:
        return self.client.auth

    def get_user_info(self):
        response = self.get_auth().get_user()
        if not response or not response.user:
            raise PermissionError("로그인 필수 기능입니다. 로그인이 필요합니다.")

        return response.user

    def get_user_type(self) -> str:
        user = self.get_user_info()
        response = (
            self.get_user_details_table()
            .select("type")
            .eq("id", user.id)
            .is_("deleted_at", "null")
            .limit(1)
            .maybe_single()
            .execute()
        )

        if response and response.data:
            return response.data["type"]
        else:
            raise LookupError(
                "회원 상세 정보가 없습니다. 상세 정보를 먼저 등록해주세요."
            )

    # ------------------------------------------------------------------
    # 테이블
    # ------------------------------------------------------------------
    def get_user_details_table(self) -> SyncRequestBuilder:
        return self.client.table("user_details")

    def get_products_table(self) -> SyncRequestBuilder:
        return self.client.table("products")

    def get_orders_table(self) -> SyncRequestBuilder:
        return self.client.table("orders")

    def get_order_items_table(self) -> SyncRequestBuilder:
        return self.client.table("order_items")

    # ------------------------------------------------------------------
    # 예외 변환
    #   PostgreSQL / PostgREST 에러 코드를 의미 있는 파이썬 예외로 바꿔준다.
    #   사용법: except APIError as e: raise self.to_app_error(e, "기본 메시지") from e
    # ------------------------------------------------------------------
    @staticmethod
    def to_app_error(e: APIError, default_message: str) -> Exception:
        match e.code:
            case "23502":  # not_null_violation
                return ValueError("필수 입력값이 누락되었습니다.")
            case "23503":  # foreign_key_violation
                return ValueError("참조하는 데이터가 존재하지 않습니다.")
            case "23505":  # unique_violation
                return ValueError("이미 존재하는 데이터입니다.")
            case "23514":  # check_violation
                return ValueError("입력값이 허용 범위를 벗어났습니다.")
            case "22P02":  # invalid_text_representation (잘못된 uuid 등)
                return ValueError("입력값 형식이 올바르지 않습니다.")
            # insufficient_privilege (RLS 위반, 컬럼 권한 없음, 함수 내 권한 검사)
            case "42501":
                if (
                    e.message
                    and "row-level security" not in e.message
                    and "permission denied" not in e.message
                ):
                    return PermissionError(e.message)
                return PermissionError("해당 데이터에 대한 권한이 없습니다.")
            case "P0001":  # 함수 안의 raise exception
                return ValueError(e.message)
            case "PGRST116":  # single() 결과 없음
                return LookupError("데이터를 찾을 수 없습니다.")
            case _:
                return RuntimeError(default_message)
