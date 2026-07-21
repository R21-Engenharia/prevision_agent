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
}

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

export type Periodo = 'Mes' | 'Trimestre' | 'Semestre' | 'Anual' | 'Tudo'

export interface AuditoriaSerie {
  mes: string
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

export interface Tempo {
  obra: string
  disponivel: boolean
  coletado_em: string | null
  dias: Array<{ data: string; condicao: string }>
  meses: Array<{ mes: string; ENSOLARADO: number; NUBLADO: number; CHUVOSO: number; total: number }>
  totais: Record<Condicao, number>
  historico: Record<Condicao, number>
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

export const api = {
  obras: () => get<{ obras: string[] }>('/api/obras'),
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
