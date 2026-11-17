-- KindleSRS tables (Supabase / Postgres). Run once in the Supabase SQL editor.
create table if not exists srs_photos (
  id             serial primary key,
  filename       text unique not null,
  drive_file_id  text,
  uploaded_at    timestamptz default now(),
  description    text,
  processed      boolean default false,
  times_used     int default 0
);

create table if not exists srs_words (
  id           serial primary key,
  word         text unique not null,
  definition   text,
  ipa          text,
  context      text,
  source_book  text,
  source_type  text,
  readwise_id  text unique,
  status       text default 'new' check (status in ('new','assigned','consolidated')),
  imported_at  timestamptz default now()
);

create table if not exists srs_cards (
  id             serial primary key,
  photo_id       int references srs_photos(id) on delete cascade,
  word_id        int references srs_words(id) on delete cascade,
  visual_anchor  text,
  memory_cue     text,
  created_at     timestamptz default now(),
  manually_added boolean default false,
  unique (photo_id, word_id)
);

create table if not exists srs_sessions (
  id           serial primary key,
  session_date date unique not null,
  photo1_id    int references srs_photos(id),
  photo2_id    int references srs_photos(id),
  story_photo1 text,
  story_photo2 text,
  email_sent   boolean default false,
  created_at   timestamptz default now()
);

create table if not exists srs_session_cards (
  session_id  int references srs_sessions(id) on delete cascade,
  card_id     int references srs_cards(id) on delete cascade,
  primary key (session_id, card_id)
);

create table if not exists srs_reviews (
  id           serial primary key,
  card_id      int references srs_cards(id) on delete cascade,
  reviewed_at  timestamptz default now(),
  result       text check (result in ('easy','hard','again')),
  consolidated boolean default false
);

create table if not exists srs_meta (
  key    text primary key,
  value  text
);

alter table srs_photos        enable row level security;
alter table srs_words         enable row level security;
alter table srs_cards         enable row level security;
alter table srs_sessions      enable row level security;
alter table srs_session_cards enable row level security;
alter table srs_reviews       enable row level security;
alter table srs_meta          enable row level security;
