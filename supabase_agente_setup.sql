-- =============================================================================
-- Agente Inteligente de Priorização de Serviços — esquema do banco
-- Rodar no Supabase: Dashboard > SQL Editor > New query
-- =============================================================================
-- Princípios de projeto:
--   1. Obra-aware  — toda tabela carrega `obra`; base para o isolamento
--      multi-tenant (viewer travado na obra, admin vê tudo).
--   2. Append-only — nada é sobrescrito. Respostas e histórico só acumulam,
--      para auditoria íntegra (requisito do spec).
--   3. Regra configurável — a lógica de prioridade vive em `priority_rules`
--      (JSONB de parâmetros), não no código. Ajustável sem deploy.
--   4. Liga no que já existe — `fvs_snapshots` (dados do serviço) e
--      `authorized_emails` (usuários/permissões), sem duplicar dado.
-- =============================================================================

-- Trigger genérico para manter `updated_at` -----------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- 1. REGRAS DE PRIORIDADE (configuráveis)
-- =============================================================================
-- Cada linha é um detector. `parametros` guarda os limiares (JSONB) para dar
-- para afinar pelo painel sem tocar em código. `severidade` é o peso base.
CREATE TABLE IF NOT EXISTS public.priority_rules (
    id            BIGSERIAL PRIMARY KEY,
    codigo        TEXT NOT NULL UNIQUE,           -- ex.: 'atraso_proprio'
    nome          TEXT NOT NULL,
    descricao     TEXT DEFAULT '',
    categoria     TEXT NOT NULL,                  -- ver enum lógico abaixo
    parametros    JSONB NOT NULL DEFAULT '{}',    -- {"gap_min": 5, "dias": 7, ...}
    severidade    INTEGER NOT NULL DEFAULT 3,     -- 1 (baixa) .. 5 (crítica)
    ativa         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
-- categoria ∈ atraso_proprio | atraso_herdado | fora_sequencia | parada |
--             nc_critica | aging | aguardando_aprovacao

DROP TRIGGER IF EXISTS trg_priority_rules_updated ON public.priority_rules;
CREATE TRIGGER trg_priority_rules_updated BEFORE UPDATE ON public.priority_rules
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Regras padrão (a lógica que validamos). ON CONFLICT preserva ajustes já feitos.
INSERT INTO public.priority_rules (codigo, nome, categoria, parametros, severidade, descricao) VALUES
  ('atraso_proprio', 'Atraso próprio',       'atraso_proprio', '{"gap_min": 5}',                  5,
   'Serviço atrasado com TODOS os predecessores concluídos — frente estava liberada.'),
  ('atraso_herdado', 'Atraso herdado',       'atraso_herdado', '{"gap_min": 5, "pred_incompleto": 99}', 3,
   'Serviço atrasado porque um predecessor está incompleto — a cobrança vai ao predecessor.'),
  ('fora_sequencia', 'Execução fora de sequência', 'fora_sequencia', '{"avanco_min": 10, "gap_pred": 20}', 4,
   'Serviço avançou antes do predecessor — risco de retrabalho.'),
  ('parada',         'Serviço parado',        'parada',         '{"dias_sem_atualizacao": 7}',    4,
   'Vinha avançando e estagnou (sem movimento no período).'),
  ('nc_critica',     'Não-conformidade crítica', 'nc_critica',  '{"nc_pendentes_min": 1}',        4,
   'FVS com não-conformidades pendentes de tratamento.'),
  ('aging',          'Pendência envelhecida', 'aging',          '{"dias_pendente_min": 30}',      3,
   'Serviço pendente há muitos dias (faixa de aging elevada).')
ON CONFLICT (codigo) DO NOTHING;

-- =============================================================================
-- 2. PENDÊNCIAS INTELIGENTES
-- =============================================================================
-- Um registro por situação detectada. `causa_raiz` guarda o diagnóstico
-- (ex.: qual predecessor está travando), `impacto` = nº de sucessores travados.
CREATE TABLE IF NOT EXISTS public.pendencias (
    id                BIGSERIAL PRIMARY KEY,
    obra              TEXT NOT NULL,
    -- Identidade do serviço (liga no Prevision/FVS sem FK rígida)
    wbs_code          TEXT NOT NULL,
    activity_id       TEXT DEFAULT '',
    servico           TEXT DEFAULT '',            -- descrição/modelo
    pavimento         TEXT DEFAULT '',
    local             TEXT DEFAULT '',
    -- Diagnóstico
    rule_id           BIGINT REFERENCES public.priority_rules(id),
    categoria         TEXT NOT NULL,              -- espelha priority_rules.categoria
    causa_raiz        JSONB DEFAULT '{}',         -- {"predecessor_wbs": "21.54", "pred_pct": 80}
    impacto           INTEGER DEFAULT 0,          -- sucessores diretos travados
    severidade        INTEGER DEFAULT 3,
    pct_real          REAL,
    pct_esperado      REAL,
    -- Responsável (empreiteiro/equipe vinda do Prevision) e ciclo de vida
    responsavel_email TEXT DEFAULT '',
    responsavel_nome  TEXT DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'aberta',
    -- status ∈ aberta | respondida | em_tratamento | resolvida | descartada
    detectada_em      TIMESTAMPTZ DEFAULT NOW(),
    encerrada_em      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Evita duplicar a mesma pendência aberta para o mesmo serviço+categoria.
-- (Índice parcial: só vale enquanto está aberta; ao resolver, pode reabrir depois.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_pendencia_aberta
  ON public.pendencias (obra, wbs_code, categoria)
  WHERE status IN ('aberta', 'respondida', 'em_tratamento');

CREATE INDEX IF NOT EXISTS idx_pendencias_obra_status ON public.pendencias (obra, status);
CREATE INDEX IF NOT EXISTS idx_pendencias_severidade  ON public.pendencias (severidade DESC, impacto DESC);

DROP TRIGGER IF EXISTS trg_pendencias_updated ON public.pendencias;
CREATE TRIGGER trg_pendencias_updated BEFORE UPDATE ON public.pendencias
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- =============================================================================
-- 3. PERGUNTAS GERADAS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.pendencia_perguntas (
    id            BIGSERIAL PRIMARY KEY,
    pendencia_id  BIGINT NOT NULL REFERENCES public.pendencias(id) ON DELETE CASCADE,
    texto         TEXT NOT NULL,
    ordem         INTEGER DEFAULT 0,
    origem        TEXT DEFAULT 'template',        -- 'template' | 'ia'
    gerada_em     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_perguntas_pendencia ON public.pendencia_perguntas (pendencia_id);

-- =============================================================================
-- 4. RESPOSTAS  (append-only — nada é sobrescrito)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.pendencia_respostas (
    id            BIGSERIAL PRIMARY KEY,
    pendencia_id  BIGINT NOT NULL REFERENCES public.pendencias(id) ON DELETE CASCADE,
    pergunta_id   BIGINT REFERENCES public.pendencia_perguntas(id),
    obra          TEXT NOT NULL,                  -- redundância proposital p/ RLS por obra
    usuario_email TEXT NOT NULL,
    usuario_nome  TEXT DEFAULT '',
    texto         TEXT NOT NULL,
    respondida_em TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_respostas_pendencia ON public.pendencia_respostas (pendencia_id, respondida_em);

-- =============================================================================
-- 5. HISTÓRICO / AUDITORIA  (linha do tempo imutável)
-- =============================================================================
-- Todo evento da pendência entra aqui: criada, pergunta gerada, respondida,
-- status alterado, e-mail enviado, reaberta, encerrada. Nunca é editado.
CREATE TABLE IF NOT EXISTS public.pendencia_historico (
    id            BIGSERIAL PRIMARY KEY,
    pendencia_id  BIGINT NOT NULL REFERENCES public.pendencias(id) ON DELETE CASCADE,
    obra          TEXT NOT NULL,
    evento        TEXT NOT NULL,                  -- criada|pergunta_gerada|respondida|status_alterado|email_enviado|reaberta|encerrada
    detalhe       JSONB DEFAULT '{}',
    usuario_email TEXT DEFAULT '',                -- vazio = ação automática do agente
    ocorrido_em   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_historico_pendencia ON public.pendencia_historico (pendencia_id, ocorrido_em);

-- =============================================================================
-- 6. LOGS DE IA
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.ia_logs (
    id             BIGSERIAL PRIMARY KEY,
    obra           TEXT DEFAULT '',
    pendencia_id   BIGINT REFERENCES public.pendencias(id) ON DELETE SET NULL,
    tipo           TEXT NOT NULL,                 -- 'chat' | 'geracao_pergunta'
    usuario_email  TEXT DEFAULT '',
    modelo         TEXT DEFAULT '',
    tokens_entrada INTEGER DEFAULT 0,
    tokens_saida   INTEGER DEFAULT 0,
    custo_usd      NUMERIC(10,5) DEFAULT 0,
    sucesso        BOOLEAN DEFAULT TRUE,
    erro           TEXT DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ia_logs_obra ON public.ia_logs (obra, created_at);

-- =============================================================================
-- 7. ENVIO DE E-MAILS  (via Resend)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.emails_enviados (
    id            BIGSERIAL PRIMARY KEY,
    obra          TEXT DEFAULT '',
    pendencia_id  BIGINT REFERENCES public.pendencias(id) ON DELETE SET NULL,
    tipo          TEXT NOT NULL,                  -- individual | consolidado_diario | consolidado_semanal
    destinatarios TEXT[] NOT NULL DEFAULT '{}',
    assunto       TEXT DEFAULT '',
    provider_id   TEXT DEFAULT '',                -- id retornado pelo Resend
    status        TEXT DEFAULT 'enviado',         -- enviado | falhou
    erro          TEXT DEFAULT '',
    enviado_em    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_emails_obra ON public.emails_enviados (obra, enviado_em);

-- =============================================================================
-- 8. ISOLAMENTO POR OBRA (multi-tenant) — coluna de escopo do usuário
-- =============================================================================
-- Viewer travado nas suas obras; admin vê tudo. `obras = NULL` significa
-- "todas" (usado por admins). A checagem forte entra na Fase 3, junto com as
-- políticas RLS; aqui só preparamos a coluna para não migrar dado depois.
ALTER TABLE public.authorized_emails
  ADD COLUMN IF NOT EXISTS obras TEXT[] DEFAULT NULL;

-- =============================================================================
-- 9. RLS — habilitado, políticas fechadas por enquanto (Fase 3 abre por obra)
-- =============================================================================
-- Por ora liberamos leitura/escrita ao papel de serviço; a API valida o token
-- e a obra na camada de aplicação. As políticas por obra entram na Fase 3.
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'priority_rules','pendencias','pendencia_perguntas','pendencia_respostas',
    'pendencia_historico','ia_logs','emails_enviados'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS "agente_service_all" ON public.%I;', t);
    EXECUTE format(
      'CREATE POLICY "agente_service_all" ON public.%I FOR ALL USING (true) WITH CHECK (true);', t);
  END LOOP;
END $$;
