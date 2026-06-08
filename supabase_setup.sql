-- =============================================================
-- FVS Dashboard — Tabela de snapshots historicos
-- Rodar no Supabase: Dashboard > SQL Editor > New query
-- =============================================================

-- 1. Tabela principal
CREATE TABLE IF NOT EXISTS public.fvs_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    date_snapshot   DATE          NOT NULL,
    obra            TEXT          NOT NULL,
    act_id          TEXT          NOT NULL,
    wbs             TEXT          DEFAULT '',
    floor           TEXT          DEFAULT '',
    cf_pct          REAL          DEFAULT 0,
    modelo          TEXT          DEFAULT '',
    local           TEXT          DEFAULT '',
    status          TEXT          DEFAULT '',
    pct_exec        REAL,
    nc              INTEGER       DEFAULT 0,
    nc_tratadas     INTEGER       DEFAULT 0,
    nc_pendentes    INTEGER       DEFAULT 0,
    data_ins        TEXT          DEFAULT '',
    link            TEXT          DEFAULT '',
    date_first_seen DATE,
    dias_pendente   INTEGER       DEFAULT 0,
    faixa_aging     TEXT          DEFAULT '',
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    CONSTRAINT fvs_snapshots_unique
        UNIQUE (date_snapshot, obra, act_id, modelo, local)
);

-- 2. Indice para queries por obra + data (as mais comuns)
CREATE INDEX IF NOT EXISTS idx_fvs_snapshots_obra_date
    ON public.fvs_snapshots (obra, date_snapshot);

-- 3. Row Level Security
ALTER TABLE public.fvs_snapshots ENABLE ROW LEVEL SECURITY;

-- Permite leitura e escrita sem autenticacao
-- (dados de obra, nao dados de usuarios — seguranca nao e requisito aqui)
DROP POLICY IF EXISTS "fvs_allow_all" ON public.fvs_snapshots;
CREATE POLICY "fvs_allow_all" ON public.fvs_snapshots
    FOR ALL USING (true) WITH CHECK (true);
