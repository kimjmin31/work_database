-- =====================================================================
-- 02_functions.sql : 트랜잭션 함수
--
-- Supabase(PostgREST)는 RPC 호출 1건을 하나의 트랜잭션으로 실행한다.
-- 함수 안에서 예외가 발생하면 그때까지의 INSERT/UPDATE 가 모두 ROLLBACK 되고,
-- 끝까지 성공해야만 COMMIT 된다.
--
-- security definer 함수는 RLS 를 우회하므로, 사용자 식별은 파라미터가 아닌
-- auth.uid() 로만 하고 권한 검사를 함수 안에서 직접 수행한다.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 주문 생성 : orders 1건 + order_items N건 + total_price 갱신을 하나의 트랜잭션으로 처리
-- ---------------------------------------------------------------------
create or replace function create_order_transaction(
  p_order_name     text,
  p_order_email    text,
  p_order_phone    text,
  p_receiver_name  text,
  p_receiver_phone text,
  p_zipcode        text,
  p_address        text,
  p_address_sub    text,
  p_delivery_memo  text,
  p_items          jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id     uuid := auth.uid();
  v_order_id    uuid;
  v_order_no    text;
  v_total_price int := 0;
  v_item        record;
  v_product     record;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.' using errcode = '42501';
  end if;

  if not exists (
    select 1 from user_details
    where id = v_user_id and type = 'BUYER' and deleted_at is null
  ) then
    raise exception '상품 구매는 일반(BUYER) 계정으로만 가능합니다.' using errcode = '42501';
  end if;

  if p_items is null or jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) = 0 then
    raise exception '주문할 상품 목록이 비어 있습니다.';
  end if;

  -- 1) 주문 헤더 생성 (total_price 는 상품 처리 후 갱신)
  insert into orders (
    user_id, order_name, order_email, order_phone,
    receiver_name, receiver_phone, zipcode, address,
    address_sub, delivery_memo, total_price, order_status
  ) values (
    v_user_id, p_order_name, p_order_email, p_order_phone,
    p_receiver_name, p_receiver_phone, p_zipcode, p_address,
    p_address_sub, p_delivery_memo, 0, 'READY'
  )
  returning id, order_no into v_order_id, v_order_no;

  -- 2) 주문 상품 생성
  for v_item in
    select
      (elem->>'product_id')::uuid as product_id,
      (elem->>'quantity')::int    as quantity
    from jsonb_array_elements(p_items) as elem
  loop
    if v_item.quantity is null or v_item.quantity <= 0 then
      raise exception '주문 수량은 1개 이상이어야 합니다.';
    end if;

    select id, name, price
      into v_product
      from products
     where id = v_item.product_id
       and deleted_at is null
       for share;  -- 주문 처리 중 상품이 삭제/변경되지 않도록 잠금

    if not found then
      raise exception '유효하지 않거나 삭제된 상품이 포함되어 있습니다. (ID: %)', v_item.product_id;
    end if;

    insert into order_items (order_id, product_id, item_name, price, quantity)
    values (v_order_id, v_product.id, v_product.name, v_product.price, v_item.quantity);

    v_total_price := v_total_price + (v_product.price * v_item.quantity);
  end loop;

  -- 3) 총 금액 갱신
  update orders
     set total_price = v_total_price
   where id = v_order_id;

  return jsonb_build_object(
    'success',     true,
    'order_id',    v_order_id,
    'order_no',    v_order_no,
    'total_price', v_total_price
  );
end;
$$;

-- ---------------------------------------------------------------------
-- 주문 취소(삭제) : orders + order_items 를 하나의 트랜잭션으로 soft delete
--   READY(결제 전) 상태의 본인 주문만 취소할 수 있다.
-- ---------------------------------------------------------------------
create or replace function cancel_order(p_order_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := auth.uid();
  v_order   record;
begin
  if v_user_id is null then
    raise exception '로그인이 필요합니다.' using errcode = '42501';
  end if;

  select id, order_no, order_status
    into v_order
    from orders
   where id = p_order_id
     and user_id = v_user_id
     and deleted_at is null
     for update;

  if not found then
    raise exception '주문을 찾을 수 없습니다. (ID: %)', p_order_id;
  end if;

  if v_order.order_status <> 'READY' then
    raise exception '결제 전(READY) 주문만 취소할 수 있습니다. (현재 상태: %)', v_order.order_status;
  end if;

  update order_items
     set deleted_at = now(), modified_at = now()
   where order_id = p_order_id;

  update orders
     set order_status = 'CANCELED', deleted_at = now(), modified_at = now()
   where id = p_order_id;

  return jsonb_build_object(
    'success',  true,
    'order_id', v_order.id,
    'order_no', v_order.order_no,
    'order_status', 'CANCELED'
  );
end;
$$;

-- 함수 실행 권한: 로그인 사용자만
revoke execute on function create_order_transaction(text, text, text, text, text, text, text, text, text, jsonb) from public, anon;
revoke execute on function cancel_order(uuid) from public, anon;
grant execute on function create_order_transaction(text, text, text, text, text, text, text, text, text, jsonb) to authenticated;
grant execute on function cancel_order(uuid) to authenticated;
