create table transactions
(
    transaction_id integer primary key generated always as identity,
    user_id        integer     references users on delete set null,
    event_id       integer     references events on delete set null,
    time           timestamptz not null default now(),
    payment_method text        not null
);

create table sales
(
    sale_id        integer primary key generated always as identity,
    transaction_id integer not null references transactions on delete cascade,
    product_id     integer references products on delete set null,
    amount         integer not null check (amount > 0),
    price          numeric not null check ( price >= 0 )
);


create view sums_by_transaction as
select t.transaction_id, coalesce(sum(s.price * s.amount), 0) as sum, coalesce(sum(s.amount), 0) as items
from transactions t
         left join sales s on t.transaction_id = s.transaction_id
group by t.transaction_id;


create view get_all_sales as
select s.sale_id,
       s.transaction_id,
       s.amount,
       s.price,
       s.product_id,
       case
           when p.product_id is null then null
           else json_build_object('product_id', p.product_id, 'name', p.name, 'stock',
                                  p.stock, 'price', p.price, 'categories',
                                  (select cbp.categories
                                   from categories_by_product cbp
                                   where cbp.product_id = s.product_id))
           end
           as product
from sales s
         left join products p on s.product_id = p.product_id;

create view get_all_transactions as
select t.transaction_id,
       t.user_id,
       case
           when t.user_id is null then null
           else json_build_object('user_id', u.user_id, 'username', u.username)
           end as "user",
       t.event_id,
       case
           when t.event_id is null then null
           else json_build_object('event_id', e.event_id, 'name', e.name, 'start', e.start, 'finish', e.finish)
           end as event,
       t.time,
       t.payment_method,
       json_agg((select json_build_object(
                                'sale_id', gas.sale_id,
                                'amount', gas.amount,
                                'price', gas.price,
                                'product_id', product_id,
                                'product', gas.product)
                 from get_all_sales gas
                 where gas.sale_id = s.sale_id)) as sales,
       sbt.sum
from transactions t
         left join users u on t.user_id = u.user_id
         left join events e on t.event_id = e.event_id
         left join sales s on t.transaction_id = s.transaction_id
         left join sums_by_transaction sbt on t.transaction_id = sbt.transaction_id
group by t.transaction_id, u.user_id, e.event_id, sbt.sum;

