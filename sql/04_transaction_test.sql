-- =====================================================================
-- 04_transaction_test.sql : COMMIT / ROLLBACK 재현 (Supabase SQL Editor 에서 블록별로 실행)
--
-- SQL Editor 는 postgres 권한으로 실행되므로, 아래처럼 구매자(BUYER) 계정으로
-- 잠시 "변신"해서 함수가 auth.uid() 를 인식하도록 한다.
-- 'user01@test.com' 은 본인이 가입시킨 구매자 이메일로 바꿔서 실행할 것.
-- =====================================================================


-- [0] 실행 전 건수 확인 ------------------------------------------------
select
  (select count(*) from orders)      as orders_count,
  (select count(*) from order_items) as order_items_count;


-- [1] 성공 시나리오 → COMMIT -------------------------------------------
begin;
  select set_config('request.jwt.claim.sub',
    (select id::text from auth.users where email = 'user01@test.com'), true);
  set local role authenticated;

  select create_order_transaction(
    '김철수', 'user01@test.com', '010-0000-0000',
    '이영희', '010-1234-5678', '3200', '받는사람 주소', '상세 주소', '문앞에 두세요.',
    jsonb_build_array(
      jsonb_build_object(
        'product_id', (select id from products where deleted_at is null limit 1),
        'quantity', 1
      )
    )
  );
commit;

-- 건수 확인 → orders +1, order_items +1
select
  (select count(*) from orders)      as orders_count,
  (select count(*) from order_items) as order_items_count;


-- [2] 실패 시나리오 → 자동 ROLLBACK --------------------------------------
--   첫 번째 상품은 정상, 두 번째 상품은 존재하지 않는 ID.
--   함수 안에서 orders, order_items 1건이 이미 insert 되었지만
--   두 번째 상품에서 예외가 발생하면서 전부 취소된다.
begin;
  select set_config('request.jwt.claim.sub',
    (select id::text from auth.users where email = 'user01@test.com'), true);
  set local role authenticated;

  select create_order_transaction(
    '김철수', 'user01@test.com', '010-0000-0000',
    '이영희', '010-1234-5678', '3200', '받는사람 주소', '상세 주소', '실패 테스트',
    jsonb_build_array(
      jsonb_build_object(
        'product_id', (select id from products where deleted_at is null limit 1),
        'quantity', 1
      ),
      jsonb_build_object(
        'product_id', '00000000-0000-0000-0000-000000000000',
        'quantity', 1
      )
    )
  );
  -- ERROR: 유효하지 않거나 삭제된 상품이 포함되어 있습니다.
rollback;

-- 건수 확인 → [1] 직후와 동일 (부분 저장 없음)
select
  (select count(*) from orders)      as orders_count,
  (select count(*) from order_items) as order_items_count;


-- [3] 명시적 ROLLBACK ---------------------------------------------------
--   정상 주문이라도 트랜잭션을 ROLLBACK 하면 저장되지 않는다.
begin;
  select set_config('request.jwt.claim.sub',
    (select id::text from auth.users where email = 'user01@test.com'), true);
  set local role authenticated;

  select create_order_transaction(
    '김철수', 'user01@test.com', '010-0000-0000',
    '이영희', '010-1234-5678', '3200', '받는사람 주소', '상세 주소', '롤백 테스트',
    jsonb_build_array(
      jsonb_build_object(
        'product_id', (select id from products where deleted_at is null limit 1),
        'quantity', 3
      )
    )
  );

  -- 트랜잭션 안에서는 보인다
  select order_no, total_price, delivery_memo from orders where delivery_memo = '롤백 테스트';
rollback;

-- 트랜잭션 밖에서는 없다 → 0 rows
select order_no, total_price, delivery_memo from orders where delivery_memo = '롤백 테스트';
