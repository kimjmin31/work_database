from dataclasses import asdict, dataclass
from typing import Literal

from postgrest.exceptions import APIError
from supabase import AuthApiError, AuthInvalidCredentialsError

from ..utils.time import get_timestamptz
from .base_service import BaseService


@dataclass(kw_only=True)
class Account:
    email: str
    password: str


@dataclass(kw_only=True)
class AccountInfo:
    type: Literal["BUYER", "SELLER"] | None = None
    cellphone: str | None = None
    zipcode: str | None = None
    address: str | None = None
    address_sub: str | None = None


class UserService(BaseService):
    # ------------------------------------------------------------------
    # 인증 (Supabase Auth → auth.users)
    # ------------------------------------------------------------------

    # 회원가입
    def sign_up(self, account: Account):
        try:
            response = self.get_auth().sign_up(
                {
                    "email": account.email,
                    "password": account.password,
                }
            )

            if not response.user:
                raise RuntimeError("가입 중 오류가 발생하였습니다.")

            return response.user
        except AuthInvalidCredentialsError as e:
            raise ValueError("계정을 다시 확인해주세요.") from e
        except AuthApiError as e:
            raise ValueError(f"가입할 수 없는 계정입니다. ({e.message})") from e

    # 로그인
    def login(self, account: Account):
        try:
            response = self.get_auth().sign_in_with_password(
                {"email": account.email, "password": account.password}
            )

            if response.user:
                return response.user
            else:
                raise PermissionError("사용자가 존재하지 않습니다.")
        except AuthApiError as e:
            raise PermissionError(f"로그인에 실패하였습니다. ({e.message})") from e

    # 로그아웃
    def logout(self):
        self.get_auth().sign_out()

    # ------------------------------------------------------------------
    # 회원 상세 정보 CRUD (public.user_details)
    # ------------------------------------------------------------------

    # [C] 회원 상세 정보 등록
    def create_details(self, info: AccountInfo):
        if not (info.cellphone and info.zipcode and info.address):
            raise ValueError("휴대폰 번호, 우편번호, 주소는 필수 입력값입니다.")

        try:
            user = self.get_user_info()
            values = {k: v for k, v in asdict(info).items() if v is not None}
            values["id"] = user.id
            response = self.get_user_details_table().insert(values).execute()

            if response and response.data:
                return response.data[0]
            else:
                raise RuntimeError("상세 정보 등록에 실패하였습니다.")
        except APIError as e:
            if e.code == "23505":
                raise ValueError("이미 상세 정보가 등록된 회원입니다.") from e
            raise self.to_app_error(
                e, "상세 정보 등록 시 문제가 발생하였습니다."
            ) from e

    # [R] 회원 상세 정보 조회
    def get_details(self) -> dict[str, any]:
        try:
            user = self.get_user_info()
            response = (
                self.get_user_details_table()
                .select("*")
                .eq("id", user.id)
                .is_("deleted_at", "null")
                .limit(1)
                .maybe_single()
                .execute()
            )

            if response and response.data:
                info = dict(response.data)
                info["email"] = user.email
                return info
            else:
                return {"id": user.id, "email": user.email}
        except APIError as e:
            raise self.to_app_error(
                e, "회원 정보 조회 시 문제가 발생하였습니다."
            ) from e

    # [U] 회원 상세 정보 수정
    def update_details(self, info: AccountInfo):
        values = {k: v for k, v in asdict(info).items() if v is not None}
        if not values:
            raise ValueError("수정할 항목이 없습니다.")

        try:
            user = self.get_user_info()
            values["modified_at"] = get_timestamptz()
            response = (
                self.get_user_details_table()
                .update(values)
                .eq("id", user.id)
                .is_("deleted_at", "null")
                .execute()
            )

            if response and response.data:
                return response.data[0]
            else:
                raise LookupError(
                    "수정할 회원 정보가 없습니다. 상세 정보를 먼저 등록해주세요."
                )
        except APIError as e:
            raise self.to_app_error(
                e, "회원 정보 수정 시 문제가 발생하였습니다."
            ) from e

    # [D] 회원 탈퇴 (soft delete)
    #   주문/상품이 회원을 참조하고 있으므로 행을 지우지 않고 deleted_at 을 기록한다.
    def withdraw(self):
        try:
            user = self.get_user_info()
            now = get_timestamptz()
            response = (
                self.get_user_details_table()
                .update({"deleted_at": now, "modified_at": now})
                .eq("id", user.id)
                .is_("deleted_at", "null")
                .execute()
            )

            if response and response.data:
                return response.data[0]
            else:
                raise LookupError("탈퇴할 회원 정보가 없습니다.")
        except APIError as e:
            raise self.to_app_error(e, "회원 탈퇴 시 문제가 발생하였습니다.") from e

    # 등록/수정 자동 선택 (기존 코드 호환용)
    def set_details(self, info: AccountInfo):
        user = self.get_user_info()
        response = (
            self.get_user_details_table()
            .select("id")
            .eq("id", user.id)
            .limit(1)
            .execute()
        )

        if response.data:
            return self.update_details(info)
        else:
            return self.create_details(info)
