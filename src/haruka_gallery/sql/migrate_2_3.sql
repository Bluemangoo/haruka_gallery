create table thumbnails
(
    image_id   integer primary key references images (id) on delete cascade,
    data       blob not null,
    created_at timestamp default current_timestamp
);

create index idx_thumbnails_created_at
    on thumbnails (created_at);

update meta
set version = 3;