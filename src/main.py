import os

from dotenv import load_dotenv
from supabase import Client, create_client

# override=True: 시스템 환경변수에 같은 이름이 있어도 .env 값을 우선 사용
load_dotenv(override=True)

url: str = os.getenv("SUPABASE_URL") or ""
key: str = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY") or ""

if not url or not key:
    raise ValueError(
        ".env 의 SUPABASE_URL 과 SUPABASE_ANON_KEY(또는 SUPABASE_PUBLISHABLE_KEY)를 확인해 주세요."
    )

client: Client = create_client(url, key)


if __name__ == "__main__":
    from src.services.product_service import ProductService
    from src.services.user_service import Account, UserService

    # 간단한 연결 확인: 로그인 없이 판매 중인 상품 목록 조회
    product_service = ProductService(client)
    print("Supabase 연결 성공. 판매 중인 상품 수:", len(product_service.search()))

    # 로그인 확인 (계정 정보는 본인 값으로 변경)
    user_service = UserService(client)
    try:
        user = user_service.login(
            Account(email="user01@test.com", password="password1234")
        )
        print("로그인 성공:", user.email)
        print(user_service.get_details())
    except PermissionError as e:
        print("로그인 실패:", e)
    finally:
        user_service.logout()

    print("\nCRUD 전체 시연은 `uv run python -m src.demo` 로 실행하세요.")