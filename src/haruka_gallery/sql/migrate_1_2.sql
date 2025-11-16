alter table galleries
    add column require_comment integer default 0 not null check ( require_comment in (0, 1) );

update meta
set version = 2;
