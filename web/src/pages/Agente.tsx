import { useCallback, useEffect, useState } from 'react'
import {
  api, CATEGORIA_LABEL,
  type AgenteDashboard, type CategoriaPendencia,
  type Pendencia, type PendenciaDetalhe,
} from '../lib/api'

interface Props { obra: string }

const CAT_COR: Record<string, string> = {
  atraso_proprio: 'var(--accent-ink)',
  fora_sequencia: '#D98A00',
  parada: '#D98A00',
  nc_critica: '#C41230',
  atraso_herdado: 'var(--muted)',
  aging: 'var(--muted)',
}

function Sev({ n }: { n: number }) {
  return (
    <span className="ag-sev" title={`Severidade ${n}`}>
      {'●'.repeat(n)}<span className="ag-sev-off">{'●'.repeat(5 - n)}</span>
    </span>
  )
}

export function Agente({ obra }: Props) {
  const [dash, setDash] = useState<AgenteDashboard | null>(null)
  const [lista, setLista] = useState<Pendencia[] | null>(null)
  const [cat, setCat] = useState<CategoriaPendencia | ''>('')
  const [sel, setSel] = useState<PendenciaDetalhe | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  const carregar = useCallback(async () => {
    setErro(null)
    try {
      const [d, l] = await Promise.all([
        api.agenteDashboard(obra),
        api.pendencias(obra, undefined, cat || undefined),
      ])
      setDash(d); setLista(l.pendencias)
    } catch (e) { setErro((e as Error).message) }
  }, [obra, cat])

  useEffect(() => { void carregar() }, [carregar])

  async function abrir(id: number) {
    setSel(null)
    try { setSel(await api.pendencia(id, obra)) } catch (e) { setErro((e as Error).message) }
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
      {/* KPIs */}
      <div className="kpis">
        <div className="kpi"><div className="lbl">Pendências abertas</div>
          <div className="val">{dash?.abertas ?? '—'}</div></div>
        <div className="kpi"><div className="lbl"><span className="tag red" />Críticas</div>
          <div className="val" style={{ color: 'var(--accent-ink)' }}>{dash?.criticas ?? '—'}</div></div>
        <div className="kpi"><div className="lbl">Serviços travados (impacto)</div>
          <div className="val">{dash?.impacto_total ?? '—'}</div></div>
      </div>

      {/* filtro por categoria */}
      <div className="ag-filtros">
        <button className={cat === '' ? 'chip on' : 'chip'} onClick={() => setCat('')}>Todas</button>
        {(Object.keys(CATEGORIA_LABEL) as CategoriaPendencia[]).map((c) => (
          <button key={c} className={cat === c ? 'chip on' : 'chip'} onClick={() => setCat(c)}>
            {CATEGORIA_LABEL[c]}{dash?.por_categoria?.[c] ? ` (${dash.por_categoria[c]})` : ''}
          </button>
        ))}
      </div>

      <div className="ag-grid">
        {/* lista priorizada */}
        <div className="panel ag-lista">
          {!lista && <div className="skel" style={{ height: 240 }} />}
          {lista?.length === 0 && <div className="empty">Nenhuma pendência neste filtro.</div>}
          {lista?.map((p) => (
            <button key={p.id} className={sel?.id === p.id ? 'ag-item sel' : 'ag-item'}
                    onClick={() => abrir(p.id)}>
              <div className="ag-item-top">
                <span className="ag-servico">{p.servico || p.wbs_code}</span>
                <span className="ag-cat" style={{ color: CAT_COR[p.categoria] }}>
                  {CATEGORIA_LABEL[p.categoria]}
                </span>
              </div>
              <div className="ag-item-wbs">{p.wbs_code}{p.pavimento && ` · ${p.pavimento}º pav`}</div>
              <div className="ag-item-mid">
                {p.pct_real != null && (
                  <span className="ag-pct">{p.pct_real.toFixed(0)}%
                    <span className="ag-pct-exp"> / {(p.pct_esperado ?? 0).toFixed(0)}%</span></span>
                )}
                {p.impacto > 0 && <span className="ag-imp">trava {p.impacto}</span>}
                <Sev n={p.severidade} />
              </div>
            </button>
          ))}
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

  const pred = p.causa_raiz?.predecessor_wbs as string | undefined

  return (
    <div className="ag-conv">
      <div className="ag-conv-head">
        <div>
          <h3>{p.servico || p.wbs_code}</h3>
          <div className="ag-conv-sub">
            {p.wbs_code} · {CATEGORIA_LABEL[p.categoria]}
            {p.pavimento && ` · ${p.pavimento}º pav`}<br />
            {p.pct_real != null && `${p.pct_real.toFixed(0)}% de ${(p.pct_esperado ?? 0).toFixed(0)}% esperado`}
            {p.impacto > 0 && ` · trava ${p.impacto} serviço(s)`}
            {pred && ` · aguardando ${pred}`}
          </div>
        </div>
        <span className={`ag-badge ${p.status}`}>{p.status}</span>
      </div>

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
