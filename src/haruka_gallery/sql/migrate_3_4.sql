create table aliases
(
    id      integer primary key autoincrement,
    name    text not null,
    gallery text not null,
    tags    text not null,
    comment text
);

update meta
set version = 4;