create table categories (
    category_id integer primary key generated always as identity,
    name text not null unique check (char_length(name) between 1 and 128)
);