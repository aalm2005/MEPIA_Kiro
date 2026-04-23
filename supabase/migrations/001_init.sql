-- Transacciones extraídas de PDFs de POS
create table if not exists transactions (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz default now(),
  source_file text,
  date        date,
  amount      numeric(12, 2),
  category    text,
  raw_json    jsonb
);

-- Resultados de auditoría generados por los agentes
create table if not exists audit_results (
  id             uuid primary key default gen_random_uuid(),
  created_at     timestamptz default now(),
  module         text not null,
  raw_result     text,
  copilot_phrase text,
  archetype      text
);
