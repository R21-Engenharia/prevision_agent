/** Cliente da API FVS (FastAPI). O Vite faz proxy de /api → :8000 */

export interface Kpis {
  pacotes_liberados: number
  total_fvs: number
  finalizada: number
  em_andamento: number
  nao_iniciada: number
  pct_finalizada: number
  pct_em_andamento: number
  pct_nao_iniciada: number
  nc_total: number
  fvs_com_nc: number
}

export interface TopModelo {
  modelo: string
  total: number
  finalizada: number
  em_andamento: number
  nao_iniciada: number
  pendentes: number
  nc: number
}

export interface EvolucaoPonto {
  data: string
  finalizada: number
  em_andamento?: number
  nao_iniciada?: number
  nc_total?: number
  total: number
}

/**
 * De onde vem a série do gráfico:
 *  - "snapshots": histórico real e congelado (estado do backlog em cada dia)
 *  - "inspecoes": aproximação — inspeções atuais agrupadas pelo mês de execução.
 *    O passado muda se uma FVS antiga for finalizada hoje.
 */
export interface EvolucaoMeta {
  fonte: 'snapshots' | 'inspecoes'
  dias_snap: number
  dias_faltam: number
}

export interface AgingFaixa {
  faixa: string
  qtd: number
}

/** Universo completo da obra no InMeta — inclui pacotes já encerrados. */
export interface ObraTotal {
  realizadas: number
  concluidas: number
  em_andamento: number
  nc_abertas: number
}

export interface Overview {
  obra: string
  obra_total: ObraTotal
  kpis: Kpis
  top_modelos: TopModelo[]
  evolucao: EvolucaoPonto[]
  evolucao_meta: EvolucaoMeta
  aging: AgingFaixa[]
  cache: { prevision: string; inmeta: string }
  cache_horas: { prevision: number | null; inmeta: number | null }
}

/**
 * A partir de quantas horas cada fonte é considerada desatualizada.
 * Prevision roda em dias úteis, então 72h cobre um fim de semana sem alarme
 * falso. InMeta atualiza diariamente.
 */
export const LIMITE_HORAS = { prevision: 72, inmeta: 36 } as const

export type StatusFVS = 'FINALIZADA' | 'EM_ANDAMENTO' | 'NAO_INICIADA'

export interface LinhaFVS {
  floor: string
  act_id: string
  wbs: string
  cf_pct: number
  modelo: string
  local: string
  status: StatusFVS
  pct_exec: number | null
  nc: number
  nc_tratadas: number
  nc_pendentes: number
  data_ins: string
  link: string
}

export interface Backlog {
  obra: string
  total: number
  rows: LinhaFVS[]
  facetas: { modelos: string[]; pavimentos: string[] }
  contagem: Record<StatusFVS, number>
}

export const STATUS_LABEL: Record<StatusFVS, string> = {
  FINALIZADA: 'Finalizada',
  EM_ANDAMENTO: 'Em andamento',
  NAO_INICIADA: 'Não iniciada',
}

/**
 * Fonte do token de acesso. O App registra isto após iniciar a sessão
 * Supabase; a API valida o Bearer em toda requisição.
 */
type ProvedorToken = () => Promise<string | null>
let provedorToken: ProvedorToken | null = null

export function setTokenProvider(p: ProvedorToken) {
  provedorToken = p
}

async function cabecalhos(): Promise<HeadersInit> {
  if (!provedorToken) return {}
  const token = await provedorToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: await cabecalhos() })
  if (res.status === 401 || res.status === 403) {
    throw new Error('Sessão expirada ou sem permissão. Entre novamente.')
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      /* resposta sem corpo JSON */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// ── Auditoria ────────────────────────────────────────────────────────────────

export type Periodo = 'Dia' | 'Semana' | 'Mes' | 'Trimestre' | 'Semestre' | 'Anual' | 'Tudo'
export type Granularidade = 'dia' | 'semana' | 'mes'

export interface AuditoriaSerie {
  data: string
  finalizada: number
  em_andamento: number
  nc_total: number
  nc_pendentes: number
  nc_tratadas: number
  total: number
}

export interface Auditoria {
  obra: string
  periodo: string
  intervalo: { de: string; ate: string }
  kpis: {
    total_insp: number
    finalizada: number
    em_andamento: number
    pct_finalizada: number
    nc_total: number
    nc_pendentes: number
    snap_nao_iniciada: number
    snap_criticas: number
    snap_nc_pendentes: number
  }
  sla: { media_dias: number; max_dias: number }
  serie: AuditoriaSerie[]
  granularidade: Granularidade
  comparativo: Array<{ mes: string; cape_town: number; holmes: number }>
  aging: AgingFaixa[]
  criticas: Array<{
    obra: string; pavimento: string; modelo: string
    local: string; dias_pendente: number; nc: number
  }>
  top_pendentes: Array<{ modelo: string; pendentes: number; nc: number }>
  dias_snapshot: number
}

// ── Decoração ────────────────────────────────────────────────────────────────

export interface LinhaGantt {
  pavimento: string
  obra: string
  inicio: string
  fim: string
  atividades: number
  pct: number
  status: string
  finalizadas: number
  atrasadas: number
  disciplinas: string
}

export interface Decoracao {
  obra: string
  vazio: boolean
  kpis: {
    total: number; finalizada: number; em_andamento: number
    nao_iniciada: number; atrasada: number; pct_medio: number; proximas_30d: number
  }
  gantt: LinhaGantt[]
  disciplinas: Array<{ disciplina: string; total: number; pct: number; cor: string }>
  pavimentos: Array<{ pavimento: string; pct: number; atividades: number }>
  alertas: Array<{
    obra: string; wbs: string; pavimento: string
    disciplina: string; servico: string; inicio: string; dias: number
  }>
  facetas: { disciplinas: string[]; status: string[] }
  intervalo: { de: string; ate: string } | null
  hoje: string
}

// ── Condição do tempo ────────────────────────────────────────────────────────

export type Condicao = 'ENSOLARADO' | 'NUBLADO' | 'CHUVOSO'

/**
 * Condição do tempo consolidada — visão única, não por obra.
 * Cada dia entra uma vez só, pela obra de maior prioridade que registrou.
 */
export interface Tempo {
  disponivel: boolean
  coletado_em: string | null
  prioridade: string[]
  dias: Array<{ data: string; condicao: string; origem: string }>
  meses: Array<{ mes: string; ENSOLARADO: number; NUBLADO: number; CHUVOSO: number; total: number }>
  inmeta: Record<Condicao, number>      // dias únicos vindos do InMeta
  historico: Record<Condicao, number>   // controle interno pré-InMeta
  totais: Record<Condicao, number>      // histórico + inmeta
  cobertura: Array<{
    obra: string
    dias_registrados: number
    dias_aproveitados: number
  }>
  dias_com_rdo: number
  sem_condicao: number
  nao_classificados: number
}

export interface FiltrosBacklog {
  status: StatusFVS[]
  modelo: string
  pavimento: string
  busca: string
}

/** URL do relatório Excel com os mesmos filtros da tela. */
export function urlExportBacklog(obra: string, f: FiltrosBacklog): string {
  const p = new URLSearchParams()
  p.set('obra', obra)
  f.status.forEach((s) => p.append('status', s))
  if (f.modelo) p.set('modelo', f.modelo)
  if (f.pavimento) p.set('pavimento', f.pavimento)
  if (f.busca.trim()) p.set('busca', f.busca.trim())
  return `/api/export/backlog?${p.toString()}`
}

/** Baixa qualquer relatório da API respeitando a autenticação. */
async function baixar(url: string, nomePadrao: string): Promise<void> {
  const res = await fetch(url, { headers: await cabecalhos() })
  if (!res.ok) {
    throw new Error(
      res.status === 401 || res.status === 403
        ? 'Sessão expirada. Entre novamente para exportar.'
        : `Falha ao gerar o relatório (HTTP ${res.status}).`,
    )
  }

  // Nome do arquivo definido pela API (Content-Disposition)
  const disp = res.headers.get('content-disposition') ?? ''
  const m = /filename\*=UTF-8''([^;]+)/i.exec(disp) ?? /filename="?([^";]+)"?/i.exec(disp)
  const nome = m ? decodeURIComponent(m[1]) : nomePadrao

  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = nome
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

/**
 * Baixa o backlog filtrado.
 * Um <a href> simples não carregaria o header Authorization e levaria 401.
 */
export function baixarRelatorio(obra: string, f: FiltrosBacklog): Promise<void> {
  return baixar(urlExportBacklog(obra, f), 'backlog_fvs.xlsx')
}

export type Formato = 'excel' | 'pdf'

/** Relatório gerencial de auditoria, no mesmo recorte da tela. */
export function baixarRelatorioAuditoria(
  obra: string, periodo: Periodo, formato: Formato,
): Promise<void> {
  const p = new URLSearchParams({ periodo, formato })
  if (obra) p.set('obra', obra)
  return baixar(`/api/export/auditoria?${p.toString()}`,
                `auditoria.${formato === 'pdf' ? 'pdf' : 'xlsx'}`)
}

/** Relatório operacional de FVS (Excel completo ou PDF resumo). */
export function baixarRelatorioFVS(
  obra: string, formato: Formato, incluirFinalizadas: boolean,
): Promise<void> {
  const p = new URLSearchParams({
    obra, formato, incluir_finalizadas: String(incluirFinalizadas),
  })
  return baixar(`/api/export/fvs?${p.toString()}`,
                `fvs.${formato === 'pdf' ? 'pdf' : 'xlsx'}`)
}

export interface IntervaloTempo { de: string; ate: string }

/** Baixa o Diário do Tempo com os mesmos períodos escolhidos na tela. */
export function baixarRelatorioTempo(
  p1?: IntervaloTempo,
  p2?: IntervaloTempo,
): Promise<void> {
  const p = new URLSearchParams()
  if (p1?.de && p1?.ate) { p.set('p1_de', p1.de); p.set('p1_ate', p1.ate) }
  if (p2?.de && p2?.ate) { p.set('p2_de', p2.de); p.set('p2_ate', p2.ate) }
  const qs = p.toString()
  return baixar(`/api/export/tempo${qs ? `?${qs}` : ''}`, 'diario_do_tempo.xlsx')
}

export type FonteRefresh = 'prevision' | 'inmeta'

export interface RespostaRefresh {
  ok: boolean
  fonte: FonteRefresh
  workflow: string
  eta_min: number | null
  mensagem: string
}

/** Dispara a coleta de uma fonte (Prevision ou InMeta) no GitHub. */
async function postRefresh(fonte: FonteRefresh): Promise<RespostaRefresh> {
  const res = await fetch(`/api/refresh/${fonte}`, {
    method: 'POST',
    headers: await cabecalhos(),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      /* sem corpo JSON */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<RespostaRefresh>
}

// ── Agente Inteligente ───────────────────────────────────────────────────────

export type CategoriaPendencia =
  | 'atraso_proprio' | 'atraso_herdado' | 'fora_sequencia'
  | 'parada' | 'nc_critica' | 'aging'

export interface Pendencia {
  id: number
  wbs_code: string
  servico: string
  categoria: CategoriaPendencia
  severidade: number
  impacto: number
  pct_real: number | null
  pct_esperado: number | null
  status: string
  pavimento: string
  causa_raiz: Record<string, unknown>
  responsavel_nome: string
  detectada_em: string
}

export interface PendenciaDetalhe extends Pendencia {
  perguntas: Array<{ id: number; texto: string; ordem: number; origem: string }>
  respostas: Array<{
    id: number; pergunta_id: number | null; usuario_nome: string
    texto: string; respondida_em: string
  }>
  historico: Array<{
    evento: string; detalhe: Record<string, unknown>
    usuario_email: string; ocorrido_em: string
  }>
}

export interface AgenteDashboard {
  obra: string
  abertas: number
  criticas: number
  impacto_total: number
  por_categoria: Record<string, number>
}

export const CATEGORIA_LABEL: Record<CategoriaPendencia, string> = {
  atraso_proprio: 'Atraso próprio',
  atraso_herdado: 'Atraso herdado',
  fora_sequencia: 'Fora de sequência',
  parada: 'Parado',
  nc_critica: 'NC crítica',
  aging: 'Envelhecida',
}

// ── RUP real de mão de obra (Camada 1) ───────────────────────────────────────

export interface RupFvs {
  obra: string
  fvs_codigo: string
  fvs_nome: string
  hh_total: number
  dias_trabalhados: number
  efetivo_medio_dia: number
  n_pavimentos: number
  pavimentos: string[]
  hh_por_funcao: Record<string, number>
  pct_compartilhado: number
  // Denominador — nulos até o Sienge entrar:
  unidade: string | null
  qtd_executada: number | null
  eap_referencia: string | null
  rup_real: number | null
}

export interface Rup {
  obra: string
  resumo: {
    fvs: number; hh_total: number; com_rup: number
    aguardando_sienge: number; depara_confirmados: number
  }
  fvs: RupFvs[]
}

export interface EapServico {
  descricao: string
  unidade: string | null
  qtd_executada: number
  qtd_orcada: number
  refs: string[]
  mao_de_obra: boolean
  n_linhas: number
  score: number
  disciplinas: string[]
  rup_previa: number | null
}

export interface DeparaItem {
  fvs_codigo: string
  fvs_nome: string
  hh_total: number
  status: 'pendente' | 'confirmado'
  confirmado: {
    eap_descricao: string | null; unidade: string | null
    qtd_executada: number | null; rup_real: number | null
  } | null
  confianca: 'alta' | 'escolher' | 'baixa' | 'sem_candidato'
  sugestoes: EapServico[]
}

export type RupStatus = 'dentro' | 'acima' | 'abaixo' | 'sem_rup' | 'sem_ref'

export interface RupBanda { min: number; max: number; med: number | null; pacotes: string[] }

export interface RupPacote {
  pacote: string; hh: number; producao: number; unidade: string | null
  rup: number | null; qtd_orcada: number; n_lotes: number; status: RupStatus
  valor_risco: number; preco: number
}

export interface RupCelula {
  celula: string; hh: number; producao: number; unidade: string | null
  rup: number | null; unidades_mistas: boolean; banda: RupBanda | null
  status: RupStatus; pacotes: RupPacote[]; valor_risco: number; preco: number
  rup_anterior?: number | null; variacao_abs?: number | null
  variacao_pct?: number | null; tendencia?: 'melhorou' | 'piorou' | 'estavel' | null
}

export type RupJanela = 'mes_atual' | 'mes_anterior' | '6m' | '12m' | 'obra'

export interface RupHierarquia {
  obra: string; janela: RupJanela
  resumo: { celulas: number; com_rup: number; dentro_faixa: number; fonte_hh: string }
  celulas: RupCelula[]
}

// ── Inteligência de Custos — material (Fase 1) ───────────────────────────────

export interface CustoPreco {
  primeiro: number; ultimo: number; min: number; max: number
  medio: number; medio_ponderado: number
}
export interface CustoTendencia {
  variacao_pct: number | null
  variacao_primeira_pct?: number
  direcao: 'alta' | 'baixa' | 'estavel' | 'sem_historico' | 'compra_unica'
  acelerando?: boolean; n_compras: number
  primeira?: number; medio?: number; ultimo?: number
}
export interface CustoItem {
  resource_id: number; descricao: string; unidade: string | null
  total_qtd: number; total_valor: number; n_compras: number; n_compras_hist?: number
  classe: 'A' | 'B' | 'C'; pct: number; pct_acum: number
  preco: CustoPreco; tendencia: CustoTendencia; fornecedores: number
}
export interface CustoAlerta {
  tipo: string; nivel: 'alto' | 'medio'; resource_id: number; descricao: string
  variacao_pct: number | null; classe: string; valor: number; texto: string
  prioridade: 'P1' | 'P2' | 'P3' | 'P4'
}
export interface CustoGrupo {
  grupo: string; total_valor: number; pct: number; pct_acum: number
  classe: 'A' | 'B' | 'C'; n_insumos: number
}
export interface CustoMaterial {
  obra: string; disponivel: boolean; mensagem?: string; janela?: RupJanela
  total_comprado?: number; n_insumos?: number
  abc_resumo?: { A: number; B: number; C: number }
  grupos?: CustoGrupo[]; itens?: CustoItem[]; alertas?: CustoAlerta[]
}

export interface CustoDesembolso {
  obra: string; disponivel: boolean; mensagem?: string
  total_a_pagar?: number; vencidas?: number; n_parcelas?: number
  janelas?: Record<string, number>
  top_fornecedores_30d?: { fornecedor_id: number; valor: number }[]
}

export const api = {
  obras: () => get<{ obras: string[] }>('/api/obras'),
  custosMaterial: (obra: string, janela: RupJanela = 'obra') =>
    get<CustoMaterial>(`/api/custos/material?obra=${encodeURIComponent(obra)}&janela=${janela}`),
  custosDesembolso: (obra: string) =>
    get<CustoDesembolso>(`/api/custos/desembolso?obra=${encodeURIComponent(obra)}`),
  rup: (obra: string) => get<Rup>(`/api/rup/camada1?obra=${encodeURIComponent(obra)}`),
  rupHierarquia: (obra: string, janela: RupJanela = 'obra', soMonitorados = true) =>
    get<RupHierarquia>(`/api/rup/hierarquia?obra=${encodeURIComponent(obra)}&janela=${janela}&so_monitorados=${soMonitorados}`),
  rupDepara: (obra: string) =>
    get<{ obra: string; itens: DeparaItem[] }>(`/api/rup/depara?obra=${encodeURIComponent(obra)}`),
  rupConfirmarDepara: async (obra: string, fvsCodigo: string, grupo: EapServico) => {
    const res = await fetch(`/api/rup/depara/confirmar?obra=${encodeURIComponent(obra)}`, {
      method: 'POST',
      headers: { ...(await cabecalhos()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ fvs_codigo: fvsCodigo, eap: grupo }),
    })
    if (!res.ok) {
      let d = `HTTP ${res.status}`
      try { const b = await res.json(); if (b?.detail) d = b.detail } catch { /* */ }
      throw new Error(d)
    }
    return res.json() as Promise<{ ok: boolean; fvs_codigo: string }>
  },
  refresh: postRefresh,
  chatAgente: async (
    obra: string, pergunta: string,
    historico: Array<{ role: 'user' | 'assistant'; content: string }>,
  ) => {
    const res = await fetch(`/api/agente/chat?obra=${encodeURIComponent(obra)}`, {
      method: 'POST',
      headers: { ...(await cabecalhos()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ pergunta, historico }),
    })
    if (!res.ok) {
      let d = `HTTP ${res.status}`
      try { const b = await res.json(); if (b?.detail) d = b.detail } catch { /* */ }
      throw new Error(d)
    }
    return res.json() as Promise<{ resposta: string; modelo: string }>
  },
  enviarRelatorio: async (obra: string) => {
    const res = await fetch(`/api/agente/enviar-relatorio?obra=${encodeURIComponent(obra)}`, {
      method: 'POST', headers: await cabecalhos(),
    })
    if (!res.ok) {
      let d = `HTTP ${res.status}`
      try { const b = await res.json(); if (b?.detail) d = b.detail } catch { /* */ }
      throw new Error(d)
    }
    return res.json() as Promise<{ ok: boolean; destinatarios: string[] }>
  },
  exportarPendencias: (obra: string, tipo: 'obra' | 'fvs', pavimento?: string | null) => {
    const p = new URLSearchParams({ obra, tipo })
    if (pavimento) p.set('pavimento', pavimento)
    return baixar(`/api/export/pendencias?${p.toString()}`, `agente_${tipo}.xlsx`)
  },
  agenteDashboard: (obra: string) =>
    get<AgenteDashboard>(`/api/agente/dashboard?obra=${encodeURIComponent(obra)}`),
  pendencias: (obra: string, status?: string, categoria?: string) => {
    const p = new URLSearchParams({ obra })
    if (status) p.set('status', status)
    if (categoria) p.set('categoria', categoria)
    return get<{ obra: string; pendencias: Pendencia[] }>(`/api/pendencias?${p.toString()}`)
  },
  pendencia: (id: number, obra: string) =>
    get<PendenciaDetalhe>(`/api/pendencias/${id}?obra=${encodeURIComponent(obra)}`),
  responder: async (id: number, obra: string, texto: string, perguntaId?: number) => {
    const res = await fetch(`/api/pendencias/${id}/responder?obra=${encodeURIComponent(obra)}`, {
      method: 'POST',
      headers: { ...(await cabecalhos()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto, pergunta_id: perguntaId ?? null }),
    })
    if (!res.ok) {
      let d = `HTTP ${res.status}`
      try { const b = await res.json(); if (b?.detail) d = b.detail } catch { /* */ }
      throw new Error(d)
    }
    return res.json()
  },
  overview: (obra: string) =>
    get<Overview>(`/api/overview?obra=${encodeURIComponent(obra)}`),
  backlog: (obra: string) =>
    get<Backlog>(`/api/backlog?obra=${encodeURIComponent(obra)}`),
  tempo: () => get<Tempo>('/api/tempo'),
  decoracao: (obra: string, disciplina: string, status: string) => {
    const p = new URLSearchParams()
    if (obra) p.set('obra', obra)
    if (disciplina) p.set('disciplina', disciplina)
    if (status) p.set('status', status)
    const qs = p.toString()
    return get<Decoracao>(`/api/decoracao${qs ? `?${qs}` : ''}`)
  },
  auditoria: (obra: string, periodo: Periodo) => {
    const p = new URLSearchParams({ periodo })
    if (obra) p.set('obra', obra)
    return get<Auditoria>(`/api/auditoria?${p.toString()}`)
  },
}
