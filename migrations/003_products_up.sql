create table products
(
    product_id integer primary key generated always as identity,
    name       text    not null unique check (char_length(name) between 1 and 128),
    stock      integer not null check ( stock >= 0 ),
    price      numeric not null check (price >= 0),
    cost numeric check (cost is null or cost >= 0),
    image      text
);

create table product_categories
(
    product_id  integer references products on delete cascade,
    category_id integer references categories on delete cascade,
    primary key (product_id, category_id)
);

create view categories_by_product as
select pc.product_id, array_agg(json_build_object('category_id', c.category_id, 'name', c.name)) as categories
from product_categories pc
         left join categories c on pc.category_id = c.category_id
group by pc.product_id;

create view get_all_products as
select p.product_id, p.name, p.stock, p.price, p.image, cbp.categories
from products p
         join categories_by_product cbp on p.product_id = cbp.product_id;