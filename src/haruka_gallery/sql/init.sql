create table meta
(
    version integer not null
);

insert into meta (version)
values (2);

create table galleries
(
    id              integer primary key autoincrement,
    name            text                not null,
    require_comment integer   default 0 not null check ( require_comment in (0, 1) ),
    created_at      timestamp default current_timestamp,
    updated_at      timestamp default current_timestamp
);

create table images
(
    id         integer primary key autoincrement,
    gallery_id integer references galleries (id) on delete cascade,
    comment    text not null,
    suffix     text not null,
    uploader   text not null,
    phash      blob not null,
    file_id    text,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp
);

create table image_tags
(
    image_id integer references images (id) on delete cascade,
    tag_id   integer references tags (id) on delete cascade,
    primary key (image_id, tag_id)
);

create table tags
(
    id   integer primary key autoincrement,
    name varchar(100) unique not null
);