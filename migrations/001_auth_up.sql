create table users
(
    user_id  integer primary key generated always as identity,
    username text  not null unique check (char_length(username) between 1 and 64),
    password bytea not null check (length(password) = 256),
    salt     bytea not null check (length(salt) = 32)
);

create table tokens
(
    token_id integer primary key generated always as identity,
    user_id  integer     not null references users on delete cascade,
    value    text        not null unique check (char_length(value) = 64),
    expires  timestamptz not null
);