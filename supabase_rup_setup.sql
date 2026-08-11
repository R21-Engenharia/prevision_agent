-- =============================================================================
-- RUP REAL DE MÃO DE OBRA — Camada 1 (numerador: Hh por FVS)
-- =============================================================================
-- Rodar UMA vez no SQL editor do Supabase (depois do supabase_agente_setup.sql).
-- Guarda o consolidado de Hh por serviço (FVS) que sai do RDO do InMeta:
--   Hh = efetivo presente no serviço × 8,8h/dia (rateado quando compartilhado).
-- O denominador (quantidade executada, via Sienge) e a própria RUP entram
-- depois, sem migrar dado — por isso as colunas de quantidade já nascem aqui,
-- nulas ("aguardando Sienge").
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.rup_hh_fvs (
    id                 BIGSERIAL PRIMARY KEY,
    obra               TEXT NOT NULL,
    fvs_codigo         TEXT NOT NULL,             -- "09.05.01"
    fvs_nome           TEXT DEFAULT '',           -- "FVS 09.05.01 - Reboco Externo"
    hh_total           NUMERIC(12,1) DEFAULT 0,   -- numerador da RUP
    dias_trabalhados   INTEGER DEFAULT 0,
    efetivo_medio_dia  NUMERIC(8,1) DEFAULT 0,
    n_pavimentos       INTEGER DEFAULT 0,
    pavimentos         JSONB DEFAULT '[]'::jsonb,
    hh_por_funcao      JSONB DEFAULT '{}'::jsonb, -- {"Pedreiro": 1949.2, ...}
    pct_compartilhado  NUMERIC(5,1) DEFAULT 0,    -- sinal p/ Camada 3 (confiança)
    -- De-para FVS→EAP (Sienge). eap_* preenchidos quando o planejamento confirma:
    unidade            TEXT DEFAULT NULL,         -- m2, m3, un... (vem do item EAP)
    eap_referencia     TEXT DEFAULT NULL,         -- código Sienge amarrado (de-para)
    eap_descricao      TEXT DEFAULT NULL,         -- descrição do item EAP confirmado
    depara_status      TEXT DEFAULT 'pendente',   -- pendente | confirmado
    -- Denominador / RUP — preenchidos quando o Sienge trouxer a quantidade:
    qtd_executada      NUMERIC(14,3) DEFAULT NULL,
    rup_real           NUMERIC(12,4) DEFAULT NULL, -- Hh / qtd_executada
    atualizado_em      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (obra, fvs_codigo)
);
CREATE INDEX IF NOT EXISTS idx_rup_hh_obra ON public.rup_hh_fvs (obra, hh_total DESC);

-- RLS: mesma política de serviço do agente (a API valida token + obra).
ALTER TABLE public.rup_hh_fvs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "rup_service_all" ON public.rup_hh_fvs;
CREATE POLICY "rup_service_all" ON public.rup_hh_fvs FOR ALL USING (true) WITH CHECK (true);
