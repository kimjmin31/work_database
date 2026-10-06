-- =====================================================================
-- 01_schema.sql : 쇼핑몰 테이블 스키마
--
-- Naming Convention
--   테이블      : snake_case 복수형            (products, orders, order_items)
--   컬럼        : snake_case                   (seller_id, created_at)
--   FK 컬럼     : <참조대상 단수형>_id         (order_id, product_id, user_id)
--   PK 제약     : pk_<table>
--   FK 제약     : fk_<table>_<column>
--   CHECK 제약  : ck_<table>_<column>
--   UNIQUE 제약 : uq_<table>_<column>
--   인덱스      : idx_<table>_<column>
--   함수        : <동사>_<대상>                 (create_order_transaction)
--   공통 컬럼   : created_at / modified_at / deleted_at (soft delete)
-- =====================================================================

-- 주문번호 생성 함수 (orders.order_no 기본값에서 사용하므로 테이블보다 먼저 생성)
create or replace function generate_date_string()
returns text
language plpgsql
as $$
begin
  return to_char(clock_timestamp(), 'YYYYMMDDHH24MISSMS');
end;
$$;

-- ---------------------------------------------------------------------
-- 회원 상세 (auth.users 와 1:1)
--   이메일/비밀번호는 Supabase Auth(auth.users)에서 관리하므로 중복 저장하지 않는다. (정규화)
-- ---------------------------------------------------------------------
create table user_details (
  id          uuid        not null,
  type        text        not null default 'BUYER',
  cellphone   text        not null,
  zipcode     text        not null,
  address     text        not null,
  address_sub text,
  created_at  timestamptz not null default now(),
  modified_at timestamptz,
  deleted_at  timestamptz,

  constraint pk_user_details primary key (id),
  constraint fk_user_details_id foreign key (id)
    references auth.users (id) on delete cascade,
  constraint ck_user_details_type check (type in ('SELLER', 'BUYER'))
);

-- ---------------------------------------------------------------------
-- 상품
-- ---------------------------------------------------------------------
create table products (
  id          uuid        not null default gen_random_uuid(),
  name        text        not null,
  description text,
  price       int         not null default 0,
  seller_id   uuid        not null,
  created_at  timestamptz not null default now(),
  modified_at timestamptz,
  deleted_at  timestamptz,

  constraint pk_products primary key (id),
  constraint fk_products_seller_id foreign key (seller_id)
    references auth.users (id),
  constraint ck_products_price check (price >= 0)
);

create index idx_products_seller_id on products (seller_id);

-- ---------------------------------------------------------------------
-- 주문
--   주문자/수령인 정보는 "주문 시점의 스냅샷"이므로 회원 정보와 별도로 저장한다.
--   (회원이 나중에 주소를 바꿔도 과거 주문의 배송지는 변하면 안 되기 때문)
-- ---------------------------------------------------------------------
create table orders (
  id             uuid        not null default gen_random_uuid(),
  order_no       text        not null default generate_date_string(),
  user_id        uuid        not null,
  order_name     text        not null,
  order_email    text        not null,
  order_phone    text        not null,
  receiver_name  text        not null,
  receiver_phone text        not null,
  zipcode        text        not null,
  address        text        not null,
  address_sub    text,
  delivery_memo  text,
  total_price    int         not null,
  order_status   text        not null default 'READY',
  created_at     timestamptz not null default now(),
  modified_at    timestamptz,
  deleted_at     timestamptz,

  constraint pk_orders primary key (id),
  constraint uq_orders_order_no unique (order_no),
  constraint fk_orders_user_id foreign key (user_id)
    references auth.users (id),
  constraint ck_orders_total_price check (total_price >= 0),
  constraint ck_orders_order_status check (order_status in (
    'READY', 'ORDER', 'IN_CASH', 'PREPARE', 'ON_DELIVERY', 'DONE_DELIVERY', 'CANCELED'
  ))
);

create index idx_orders_user_id on orders (user_id);

-- ---------------------------------------------------------------------
-- 주문 상품 (orders : products = N : M 을 풀어주는 연결 테이블)
--   item_name, price 는 주문 시점 가격을 보존하기 위한 스냅샷 컬럼이다.
-- ---------------------------------------------------------------------
create table order_items (
  id          uuid        not null default gen_random_uuid(),
  order_id    uuid        not null,
  product_id  uuid        not null,
  item_name   text        not null,
  price       int         not null,
  quantity    int         not null,
  created_at  timestamptz not null default now(),
  modified_at timestamptz,
  deleted_at  timestamptz,

  constraint pk_order_items primary key (id),
  constraint fk_order_items_order_id foreign key (order_id)
    references orders (id),
  constraint fk_order_items_product_id foreign key (product_id)
    references products (id),
  constraint uq_order_items_order_id_product_id unique (order_id, product_id),
  constraint ck_order_items_price check (price >= 0),
  constraint ck_order_items_quantity check (quantity >= 1)
);

create index idx_order_items_order_id on order_items (order_id);
create index idx_order_items_product_id on order_items (product_id);
