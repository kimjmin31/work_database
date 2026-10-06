-- =====================================================================
-- 03_rls.sql : Row Level Security 정책
--
-- 원칙
--   - 모든 테이블 RLS 활성화 (정책이 없는 동작은 기본 거부)
--   - 본인 데이터만 조회/수정 (auth.uid() 기준)
--   - 물리 삭제(DELETE) 정책은 두지 않는다 → 삭제는 deleted_at 을 채우는 soft delete
--   - 주문 생성/취소는 트랜잭션 함수(create_order_transaction, cancel_order)로만 가능
-- =====================================================================

alter table user_details enable row level security;
alter table products     enable row level security;
alter table orders       enable row level security;
alter table order_items  enable row level security;

-- ---------------------------------------------------------------------
-- user_details : 본인 정보만 등록/조회/수정
-- ---------------------------------------------------------------------
create policy user_details_select_own on user_details
  for select to authenticated
  using (id = auth.uid());

create policy user_details_insert_own on user_details
  for insert to authenticated
  with check (id = auth.uid());

create policy user_details_update_own on user_details
  for update to authenticated
  using (id = auth.uid())
  with check (id = auth.uid());

-- ---------------------------------------------------------------------
-- products : 누구나 판매 중인 상품 조회, SELLER 만 본인 상품 등록/수정
--   select 정책에 "본인 상품"을 포함해야 soft delete(UPDATE ... RETURNING) 후에도
--   변경된 행을 돌려받을 수 있다.
-- ---------------------------------------------------------------------
create policy products_select_public on products
  for select to anon, authenticated
  using (deleted_at is null or seller_id = auth.uid());

create policy products_insert_seller on products
  for insert to authenticated
  with check (
    seller_id = auth.uid()
    and exists (
      select 1 from user_details
      where id = auth.uid() and type = 'SELLER' and deleted_at is null
    )
  );

create policy products_update_own on products
  for update to authenticated
  using (seller_id = auth.uid())
  with check (seller_id = auth.uid());

-- ---------------------------------------------------------------------
-- orders : 본인 주문만 조회, 결제 전(READY) 주문의 배송 정보만 수정
--   INSERT 정책 없음 → 클라이언트가 직접 insert 불가, 함수로만 생성
-- ---------------------------------------------------------------------
create policy orders_select_own on orders
  for select to authenticated
  using (user_id = auth.uid());

create policy orders_update_own_ready on orders
  for update to authenticated
  using (user_id = auth.uid() and order_status = 'READY' and deleted_at is null)
  with check (user_id = auth.uid());

-- RLS 는 "행" 단위 제어이므로, 금액/상태 같은 컬럼은 컬럼 권한으로 막는다.
revoke update on orders from anon, authenticated;
grant update (receiver_name, receiver_phone, zipcode, address, address_sub, delivery_memo, modified_at)
  on orders to authenticated;

-- ---------------------------------------------------------------------
-- order_items : 본인 주문에 속한 상품만 조회 (변경은 함수로만)
-- ---------------------------------------------------------------------
create policy order_items_select_own on order_items
  for select to authenticated
  using (
    exists (
      select 1 from orders o
      where o.id = order_items.order_id and o.user_id = auth.uid()
    )
  );
