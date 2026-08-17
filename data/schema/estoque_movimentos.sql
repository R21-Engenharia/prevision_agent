-- Trilha de auditoria das movimentações de estoque feitas pelo app.
-- Rodar no Supabase (SQL Editor) uma vez. As baixas gravam no Sienge de qualquer
-- forma; esta tabela guarda o RASTRO (quem, o quê, quando, retorno do Sienge) e
-- habilita o estorno e o histórico na tela.
create table if not exists public.estoque_movimentos (
  id                  bigint generated always as identity primary key,
  criado_em           timestamptz not null default now(),
  usuario             text        not null,          -- email do admin que gravou
  obra                text        not null,
  resource_id         text        not null,          -- insumo (mesmo id do Sienge/compras)
  descricao           text,
  operacao            text        not null,          -- baixa | entrada | estorno
  movement_type_id    int         not null,          -- tipo Sienge (2 consumo, 9 entrada avulsa...)
  quantidade          numeric     not null,
  unidade             text,
  document_id         text,
  movement_date       date,
  sienge_status       int,                            -- HTTP status da gravação
  sienge_movement_id  text,                           -- id devolvido pelo Sienge (se houver)
  sienge_resposta     jsonb,                          -- corpo da resposta (rastro completo)
  estorno_de          bigint      references public.estoque_movimentos(id),
  estornado           boolean     not null default false
);

create index if not exists estoque_movimentos_obra_idx on public.estoque_movimentos (obra, criado_em desc);

-- Mesma política aberta dos demais módulos (o acesso é controlado na API por admin).
alter table public.estoque_movimentos enable row level security;
create policy estoque_movimentos_all on public.estoque_movimentos
  for all using (true) with check (true);
