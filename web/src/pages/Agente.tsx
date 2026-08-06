import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  api, CATEGORIA_LABEL,
  type Pendencia, type PendenciaDetalhe,
} from '../lib/api'

interface Props { obra: string }

/** Nome curto do pacote para o eixo: tira o prefixo "ALV | ". */
const curto = (s: string) => {
  const p = s.split('|')
  return (p.length > 1 ? p[1] : p[0]).trim()
}

/** Rótulo curto do pavimento: "20º PV - TIPO" → "20º". */
const pavCurto = (n: string) => {
  const m = n.match(/^\d+\s*º/)
  return m ? m[0].replace(/\s/g, '') : n.split(/[-|]/)[0].trim()
}

interface Grupo { servico: string; itens: Pendencia[]; maxImpacto: number }

/** Agrupa as pendências por pacote (serviço); dentro, ordena por pavimento. */
function agrupar(lista: Pendencia[]): Grupo[] {
  const m = new Map<string, Pendencia[]>()
  for (const p of lista) {
    const k = p.servico || p.wbs_code
    const arr = m.get(k) ?? []
    arr.push(p)
    m.set(k, arr)
  }
  return [...m.entries()]
    .map(([servico, itens]) => ({
      servico,
      itens: itens.sort((a, b) =>
        (a.pavimento || '').localeCompare(b.pavimento || '', undefined, { numeric: true })),
      maxImpacto: Math.max(...itens.map((i) => i.impacto)),
    }))
    .sort((a, b) => b.maxImpacto - a.maxImpacto)
}

interface CausaRaiz {
  provavel_so_fvs?: boolean
  jobs_pendentes?: Array<{ name: string; pct: number }>
  predecessor_wbs?: string
  predecessor_servico?: string
  pred_pct?: number
  trava?: Array<{ wbs: string; servico: string; pct: number; pavimento?: string }>
}

/** "17º PV - TIPO" → "17º" */
const pavCurtoTxt = (n: string) => {
  const m = (n || '').match(/^\d+\s*º/)
  return m ? m[0].replace(/\s/g, '') : n
}

type Aba = 'obra' | 'fvs'

export function Agente({ obra }: Props) {
  const [lista, setLista] = useState<Pendencia[] | null>(null)
  const [aba, setAba] = useState<Aba>('obra')
  const [floorSel, setFloorSel] = useState<string | null>(null)
  const [sel, setSel] = useState<PendenciaDetalhe | null>(null)
  const [expandido, setExpandido] = useState<Set<string>>(new Set())
  const [erro, setErro] = useState<string | null>(null)

  const toggle = (k: string) => setExpandido((s) => {
    const n = new Set(s)
    n.has(k) ? n.delete(k) : n.add(k)
    return n
  })

  const carregar = useCallback(async () => {
    setErro(null)
    try {
      const l = await api.pendencias(obra)
      setLista(l.pendencias)
    } catch (e) { setErro((e as Error).message) }
  }, [obra])

  useEffect(() => { void carregar() }, [carregar])

  async function abrir(id: number) {
    setSel(null)
    try { setSel(await api.pendencia(id, obra)) } catch (e) { setErro((e as Error).message) }
  }

  // Separa as duas naturezas e agrega cada uma. Tudo client-side, sem chamada extra.
  const dados = useMemo(() => {
    if (!lista) return null
    const obra: Pendencia[] = []
    const fvs: Pendencia[] = []
    for (const p of lista) {
      const soFvs = (p.causa_raiz as CausaRaiz)?.provavel_so_fvs
      ;(soFvs ? fvs : obra).push(p)
    }

    // Atrasos de obra: pacotes que mais travam (por impacto)
    const pkg = new Map<string, { nome: string; impacto: number; pav: number }>()
    for (const p of obra) {
      const k = p.servico || p.wbs_code
      const c = pkg.get(k) ?? { nome: k, impacto: 0, pav: 0 }
      c.impacto += p.impacto; c.pav += 1; pkg.set(k, c)
    }
    const topPkg = [...pkg.values()]
      .map((v) => ({ ...v, label: curto(v.nome) }))
      .sort((a, b) => b.impacto - a.impacto).slice(0, 7)

    // FVS pendentes: onde estão (por pavimento) e quanto impacto de cronograma somam
    const pav = new Map<string, number>()
    for (const p of fvs) {
      const k = p.pavimento || '—'
      pav.set(k, (pav.get(k) ?? 0) + 1)
    }
    const topPav = [...pav.entries()]
      .map(([nome, qtd]) => ({ nome, label: pavCurto(nome), qtd }))
      .sort((a, b) => b.qtd - a.qtd).slice(0, 12)

    const travados = obra.reduce((s, p) => s + p.impacto, 0)
    return { obra, fvs, topPkg, topPav, travados, pacotesFvs: new Set(fvs.map(p => p.servico)).size }
  }, [lista])

  const ativa = aba === 'obra' ? dados?.obra : dados?.fvs
  const visivel = floorSel && ativa ? ativa.filter((p) => p.pavimento === floorSel) : ativa

  // trocar de aba limpa o filtro de pavimento
  useEffect(() => { setFloorSel(null) }, [aba])

  /** Clique numa barra do gráfico → expande o pacote na lista. */
  const focarPacote = (nome: string) => {
    setAba('obra')
    setExpandido((s) => new Set(s).add(nome))
    document.getElementById('ag-lista-top')?.scrollIntoView({ behavior: 'smooth' })
  }

  if (erro) {
    return (
      <div className="errbox">
        <b>Não foi possível carregar o agente</b>
        {erro} — confirme que o SQL do agente foi aplicado no Supabase.
      </div>
    )
  }

  return (
    <div className="ag">
      {/* seletor de visão — separa obra de ficha */}
      <div className="ag-tabs">
        <button className={aba === 'obra' ? 'ag-tab on obra' : 'ag-tab'} onClick={() => setAba('obra')}>
          <span className="ag-tab-n">{dados?.obra.length ?? '—'}</span>
          <div className="ag-tab-txt">
            <span className="ag-tab-t">Atrasos de obra</span>
            <span className="ag-tab-d">serviços que travam o cronograma</span>
          </div>
        </button>
        <button className={aba === 'fvs' ? 'ag-tab on fvs' : 'ag-tab'} onClick={() => setAba('fvs')}>
          <span className="ag-tab-n">{dados?.fvs.length ?? '—'}</span>
          <div className="ag-tab-txt">
            <span className="ag-tab-t">Pendências de FVS</span>
            <span className="ag-tab-d">obra ~pronta, falta preencher a ficha</span>
          </div>
        </button>
      </div>

      {/* dashboard da aba ativa */}
      <div className="panel ag-chart ag-chart-full">
        {aba === 'obra' ? (
          <>
            <div className="ag-chart-head">
              <h3>Onde atacar primeiro</h3>
              <small>pacotes que mais travam a obra — clique numa barra para abrir</small>
            </div>
            {dados ? (
              <ResponsiveContainer width="100%" height={Math.max(180, dados.topPkg.length * 34)}>
                <BarChart data={dados.topPkg} layout="vertical"
                          margin={{ top: 4, right: 44, bottom: 0, left: 6 }} barCategoryGap={9}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="label" width={190} tickLine={false} axisLine={false}
                         tick={{ fontSize: 12, fill: 'var(--ink-2)' }} />
                  <Tooltip cursor={{ fill: 'var(--surface-2)' }}
                           content={({ active, payload }) => active && payload?.length ? (
                             <div className="ag-tip"><b>{payload[0].payload.nome}</b>
                               <span>trava {payload[0].value} serviços · {payload[0].payload.pav} pav</span></div>) : null} />
                  <Bar dataKey="impacto" fill="var(--accent)" radius={[0, 4, 4, 0]} cursor="pointer"
                       onClick={(d) => { const n = (d as { nome?: string })?.nome; if (n) focarPacote(n) }}>
                    <LabelList dataKey="impacto" position="right"
                               style={{ fill: 'var(--ink-2)', fontSize: 11.5, fontWeight: 700 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="skel" style={{ height: 240 }} />}
          </>
        ) : (
          <>
            <div className="ag-chart-head">
              <h3>FVS pendentes por pavimento</h3>
              <small>onde concentrar a equipe de qualidade para fechar as fichas</small>
            </div>
            {dados ? (
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={dados.topPav} margin={{ top: 12, right: 10, bottom: 0, left: -20 }}
                          barCategoryGap={6}>
                  <XAxis dataKey="label" tickLine={false} axisLine={false}
                         tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                  <YAxis tickLine={false} axisLine={false} allowDecimals={false}
                         tick={{ fontSize: 10.5, fill: 'var(--faint)' }} />
                  <Tooltip cursor={{ fill: 'var(--surface-2)' }}
                           content={({ active, payload }) => active && payload?.length ? (
                             <div className="ag-tip"><b>{payload[0].payload.nome}</b>
                               <span>{payload[0].value} FVS pendentes</span></div>) : null} />
                  <Bar dataKey="qtd" fill="var(--ok)" radius={[4, 4, 0, 0]} cursor="pointer"
                       onClick={(d) => { const n = (d as { nome?: string })?.nome; if (n) setFloorSel(n) }}>
                    <LabelList dataKey="qtd" position="top"
                               style={{ fill: 'var(--muted)', fontSize: 10.5, fontWeight: 600 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="skel" style={{ height: 230 }} />}
          </>
        )}
      </div>

      {/* barra de ações: filtro ativo + exportar */}
      <div className="ag-actions">
        <div className="ag-actions-l">
          {floorSel && (
            <button className="ag-clear" onClick={() => setFloorSel(null)}>
              {pavCurto(floorSel)} — {floorSel} <span>×</span>
            </button>
          )}
        </div>
        <button className="btn ag-export"
                onClick={() => { void api.exportarPendencias(obra, aba, floorSel).catch((e) => setErro((e as Error).message)) }}>
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
          </svg>
          Exportar relatório
        </button>
      </div>

      <div className="ag-grid" id="ag-lista-top">
        {/* lista agrupada por pacote */}
        <div className="panel ag-lista">
          {!visivel && <div className="skel" style={{ height: 240 }} />}
          {visivel?.length === 0 && (
            <div className="empty">
              {floorSel ? 'Nada neste pavimento.'
                : aba === 'obra' ? 'Nenhum atraso de obra. 🎉' : 'Nenhuma FVS pendente. 🎉'}
            </div>
          )}
          {visivel && agrupar(visivel).map((g) => {
            const aberto = expandido.has(g.servico)
            return (
              <div key={g.servico} className="ag-pkg">
                <button className="ag-pkg-head" onClick={() => toggle(g.servico)}>
                  <span className={aberto ? 'ag-caret open' : 'ag-caret'}>▸</span>
                  <span className="ag-pkg-nome">{g.servico}</span>
                  <span className="ag-pkg-meta">{g.itens.length} pav</span>
                  {aba === 'obra' && g.maxImpacto > 0 && <span className="ag-imp">trava {g.maxImpacto}</span>}
                </button>
                {aberto && (
                  <div className="ag-pkg-body">
                    {g.itens.map((p) => {
                      const cr = (p.causa_raiz ?? {}) as CausaRaiz
                      const jobs = cr.jobs_pendentes ?? []
                      return (
                        <button key={p.id}
                                className={sel?.id === p.id ? 'ag-flr sel' : 'ag-flr'}
                                onClick={() => abrir(p.id)}>
                          <div className="ag-flr-top">
                            <span className="ag-flr-pav">{p.pavimento || p.wbs_code}</span>
                            <span className="ag-flr-pct">{(p.pct_real ?? 0).toFixed(0)}%</span>
                          </div>
                          <div className="ag-bar">
                            <span className={aba === 'fvs' ? 'ok' : ''}
                                  style={{ width: `${p.pct_real ?? 0}%` }} />
                          </div>
                          {jobs.length > 0 && (
                            <div className="ag-jobs">
                              falta: {jobs.slice(0, 3).map((j) => j.name).join(', ')}
                              {jobs.length > 3 ? '…' : ''}
                            </div>
                          )}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* detalhe / conversa */}
        <div className="panel ag-detalhe">
          {!sel && <div className="empty">Selecione uma pendência para ver a conversa.</div>}
          {sel && <Detalhe key={sel.id} p={sel} obra={obra} onResponder={() => abrir(sel.id)} />}
        </div>
      </div>
    </div>
  )
}

function Detalhe({ p, obra, onResponder }: {
  p: PendenciaDetalhe; obra: string; onResponder: () => void
}) {
  const [texto, setTexto] = useState('')
  const [perguntaId, setPerguntaId] = useState<number | undefined>()
  const [enviando, setEnviando] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  async function enviar() {
    if (!texto.trim()) return
    setEnviando(true); setMsg(null)
    try {
      await api.responder(p.id, obra, texto.trim(), perguntaId)
      setTexto(''); setPerguntaId(undefined); onResponder()
    } catch (e) { setMsg((e as Error).message) }
    finally { setEnviando(false) }
  }

  const cr = (p.causa_raiz ?? {}) as CausaRaiz
  const trava = cr.trava ?? []

  return (
    <div className="ag-conv">
      <div className="ag-conv-head">
        <div>
          <h3>{p.servico || p.wbs_code}</h3>
          <div className="ag-conv-sub">
            {p.wbs_code} · {CATEGORIA_LABEL[p.categoria]}
            {p.pavimento && ` · ${p.pavimento}`}<br />
            {p.pct_real != null && `${p.pct_real.toFixed(0)}% de ${(p.pct_esperado ?? 0).toFixed(0)}% esperado`}
          </div>
        </div>
        <span className={`ag-badge ${p.status}`}>{p.status}</span>
      </div>

      {/* serviços reais que este atraso está segurando */}
      {trava.length > 0 && (
        <div className="ag-trava">
          <div className="ag-trava-h">Está segurando {p.impacto} serviço(s) a jusante:</div>
          <div className="ag-trava-lista">
            {trava.map((t, i) => (
              <span key={i} className="ag-trava-item">
                {t.servico || t.wbs}
                {t.pavimento && <b> {pavCurtoTxt(t.pavimento)}</b>}
                <i>{(t.pct ?? 0).toFixed(0)}%</i>
              </span>
            ))}
            {p.impacto > trava.length && <span className="ag-trava-mais">+{p.impacto - trava.length}</span>}
          </div>
        </div>
      )}

      {/* serviço que vem antes (fora de sequência) */}
      {cr.predecessor_servico && (
        <div className="ag-trava aguardando">
          <div className="ag-trava-h">
            Executado antes de: <b>{cr.predecessor_servico}</b> ({cr.predecessor_wbs}) — só {(cr.pred_pct ?? 0).toFixed(0)}%
          </div>
        </div>
      )}

      {/* perguntas do agente */}
      <div className="ag-perguntas">
        {p.perguntas.map((q) => (
          <button key={q.id}
                  className={perguntaId === q.id ? 'ag-q sel' : 'ag-q'}
                  onClick={() => setPerguntaId(perguntaId === q.id ? undefined : q.id)}>
            {q.texto}
          </button>
        ))}
      </div>

      {/* respostas (linha do tempo) */}
      {p.respostas.length > 0 && (
        <div className="ag-respostas">
          {p.respostas.map((r) => (
            <div key={r.id} className="ag-resp">
              <div className="ag-resp-meta">
                <b>{r.usuario_nome || 'usuário'}</b>
                <span>{new Date(r.respondida_em).toLocaleString('pt-BR')}</span>
              </div>
              <div className="ag-resp-txt">{r.texto}</div>
            </div>
          ))}
        </div>
      )}

      {/* responder */}
      <div className="ag-form">
        <textarea value={texto} onChange={(e) => setTexto(e.target.value)}
                  placeholder={perguntaId ? 'Respondendo à pergunta selecionada…' : 'Escreva uma resposta ou justificativa…'}
                  rows={3} />
        {msg && <div className="ag-msg erro">{msg}</div>}
        <button className="btn" onClick={() => void enviar()} disabled={enviando || !texto.trim()}>
          {enviando ? 'Enviando…' : 'Responder'}
        </button>
      </div>
    </div>
  )
}
