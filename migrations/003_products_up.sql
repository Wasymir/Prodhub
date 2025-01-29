create table products (
    product_id integer primary key generated always as identity,
    name text not null unique check (char_length(name) between 1 and 128),
    stock integer not null check ( stock >= 0 ),
    price numeric not null check (price >= 0),
    image text
);

create table product_categories (
    product_id integer references products on delete cascade,
    category_id integer references categories on delete cascade,
    primary key (product_id, category_id)
);