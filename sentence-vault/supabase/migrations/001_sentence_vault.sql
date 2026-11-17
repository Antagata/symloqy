-- ============================================================
-- Sentence Vault table. Run once in the Supabase SQL Editor
-- (or with `supabase db push`). Additive only.
-- ============================================================

create table if not exists sentence_vault (
  id                bigint generated always as identity primary key,
  sentence          text not null,
  keyword           text,
  category          text,
  tags              text[],
  source            text,
  favorite          boolean default true,
  created_at        timestamptz default now(),
  last_practiced_at timestamptz,
  practice_count    integer default 0
);

create index if not exists sentence_vault_created_at_idx on sentence_vault(created_at desc);
create index if not exists sentence_vault_keyword_idx    on sentence_vault(keyword);
create index if not exists sentence_vault_category_idx   on sentence_vault(category);
create index if not exists sentence_vault_tags_idx       on sentence_vault using gin(tags);

alter table sentence_vault enable row level security;
-- No policy added on purpose: the backend talks to Supabase using the
-- service-role key, which bypasses RLS. This just blocks the anon/public
-- key from reading or writing this table directly.
