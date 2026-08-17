import { useEffect, useState } from 'react'
import {
  api, type EstoqueInsumo, type EstoqueItem, type EstoqueMaterial,
  type EstoqueMovimento, type EstoqueStatus,
} from '../lib/api'
import { CountUp } from '../components/CountUp'

const rs = (n: number) => `R$ ${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
const qt = (n: number, u: string) => `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${u}`
const dataFmt = (d?: string | null) => (d && d.length >= 10 ? d.slice(0, 10).split('-').reverse().join('/') : '—')

const STATUS_ROT: Record<EstoqueStatus, string> = {
  ruptura: 'Ruptura', critico: 'Crítico', baixo: 'Baixo', ok: 'Saudável', parado: 'Parado',
}

function Kpi({ label, valor, prefixo, sub, tom }: {
  label: string; valor: number; prefixo?: string; sub?: string; tom?: 'alerta'
}) {
  return (
    <div className="kpi">
      <div className="lbl"><span className={tom ? 'tag red' : 'tag'} />{label}</div>
      <div className="val num" style={tom ? { color: 'var(--accent-ink)' } : undefined}>
        {prefixo}<CountUp value={valor} />
      </div>
      {sub && <div className="foot"><span className="delta">{sub}</span></div>}
    </div>
  )
}

function Cobertura({ i }: { i: EstoqueItem }) {
  if (i.status === 'ruptura') return <span className="es-cob es-rup">zerado</span>
  if (i.cobertura_dias == null) return <span className="mut">—</span>
  const cls = i.cobertura_dias < 7 ? 'es-rup' : i.cobertura_dias < 15 ? 'es-crit' : ''
  return <span className={`es-cob ${cls}`}>{i.cobertura_dias} dias</span>
}

/** Painel de escrita (admin): baixa/entrada com busca do insumo e confirmação. */
function Movimentar({ obra, onDone }: { obra: string; onDone: () => void }) {
  const [op, setOp] = useState<'baixa' | 'entrada'>('baixa')
  const [q, setQ] = useState('')
  const [opcoes, setOpcoes] = useState<EstoqueInsumo[]>([])
  const [sel, setSel] = useState<EstoqueInsumo | null>(null)
  const [qtd, setQtd] = useState('')
  const [confirmar, setConfirmar] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'erro'; txt: string } | null>(null)

  useEffect(() => {
    if (sel) return
    const t = setTimeout(() => {
      if (q.trim().length >= 2) api.estoqueInsumos(obra, q).then((r) => setOpcoes(r.itens ?? [])).catch(() => setOpcoes([]))
      else setOpcoes([])
    }, 300)
    return () => clearTimeout(t)
  }, [q, obra, sel])

  const saldo = sel?.saldo ?? 0
  const n = parseFloat((qtd || '').replace(',', '.')) || 0
  const apos = op === 'baixa' ? saldo - n : saldo + n
  const excede = op === 'baixa' && n > saldo

  function limpar() { setSel(null); setQ(''); setQtd(''); setOpcoes([]); setConfirmar(false) }

  async function submeter() {
    if (!sel || n <= 0) return
    setBusy(true); setMsg(null)
    try {
      const fn = op === 'baixa' ? api.estoqueBaixa : api.estoqueEntrada
      const r = await fn(obra, sel.resource_id, n)
      setMsg({
        tipo: 'ok',
        txt: `${op === 'baixa' ? 'Baixa' : 'Entrada'} de ${qt(n, sel.unidade)} — ${sel.descricao} — gravada no Sienge`
          + `${r.sienge_movement_id ? ` (mov ${r.sienge_movement_id})` : ''}.`
          + `${r.auditoria && !r.auditoria.ok ? ' ⚠ Auditoria não gravou: ' + (r.auditoria.motivo ?? '') : ''}`,
      })
      limpar(); onDone()
    } catch (e) { setMsg({ tipo: 'erro', txt: (e as Error).message }) }
    finally { setBusy(false) }
  }

  return (
    <div className="panel">
      <div className="phead"><div><h2>Movimentar estoque</h2>
        <div className="ph-sub">Grava direto no Sienge. <b>Baixa</b> = consumo (saída) · <b>Entrada</b> = ajuste
          manual de entrada. Toda movimentação fica auditada.</div></div></div>

      <div className="es-mov">
        <div className="es-op">
          <button className={op === 'baixa' ? 'on' : ''} onClick={() => { setOp('baixa'); setConfirmar(false) }}>Baixa (consumo)</button>
          <button className={op === 'entrada' ? 'on' : ''} onClick={() => { setOp('entrada'); setConfirmar(false) }}>Entrada</button>
        </div>

        {!sel ? (
          <div className="es-busca">
            <input placeholder="Buscar insumo pela descrição (mín. 2 letras)…" value={q}
                   onChange={(e) => setQ(e.target.value)} />
            {opcoes.length > 0 && (
              <div className="es-opcoes">
                {opcoes.map((o) => (
                  <button key={o.resource_id} onClick={() => { setSel(o); setConfirmar(false) }}>
                    <span className="es-op-desc">{o.descricao}</span>
                    <span className="mut num">saldo {qt(o.saldo, o.unidade)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="es-form">
            <div className="es-sel">
              <div><b>{sel.descricao}</b><div className="mut num">saldo atual {qt(saldo, sel.unidade)}</div></div>
              <button className="es-troca" onClick={limpar}>trocar</button>
            </div>
            <div className="es-qtd">
              <label>Quantidade ({sel.unidade})
                <input type="text" inputMode="decimal" value={qtd} autoFocus
                       onChange={(e) => { setQtd(e.target.value); setConfirmar(false) }} placeholder="0" />
              </label>
              {n > 0 && (
                <div className={`es-apos ${excede ? 'es-apos-erro' : ''}`}>
                  saldo {qt(saldo, sel.unidade)} → <b>{qt(apos, sel.unidade)}</b> após a {op}
                  {excede && <span className="es-warn"> — baixa maior que o saldo</span>}
                </div>
              )}
            </div>
            {!confirmar ? (
              <button className="es-btn" disabled={n <= 0 || excede} onClick={() => setConfirmar(true)}>
                Revisar {op}
              </button>
            ) : (
              <div className="es-confirmar">
                <span>Confirmar {op} de <b>{qt(n, sel.unidade)}</b> no Sienge?</span>
                <div className="es-conf-bts">
                  <button className="es-cancel" onClick={() => setConfirmar(false)} disabled={busy}>Cancelar</button>
                  <button className="es-btn" onClick={submeter} disabled={busy}>
                    {busy ? 'Gravando…' : `Confirmar ${op}`}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {msg && <div className={`es-msg es-msg-${msg.tipo}`}>{msg.txt}</div>}
      </div>
    </div>
  )
}

/** Histórico de movimentações manuais + estorno (admin). */
function Historico({ obra, refreshKey, onDone }: { obra: string; refreshKey: number; onDone: () => void }) {
  const [movs, setMovs] = useState<EstoqueMovimento[] | null>(null)
  const [disp, setDisp] = useState(true)
  const [busy, setBusy] = useState<number | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    api.estoqueMovimentos(obra).then((r) => { setMovs(r.movimentos ?? []); setDisp(r.disponivel) }).catch(() => setMovs([]))
  }, [obra, refreshKey])

  async function estornar(id: number) {
    if (!window.confirm('Estornar esta movimentação? Um movimento compensatório será gravado no Sienge.')) return
    setBusy(id); setErro(null)
    try { await api.estoqueEstorno(id); onDone() }
    catch (e) { setErro((e as Error).message) }
    finally { setBusy(null) }
  }

  if (!disp) return (
    <div className="panel"><div className="phead"><div><h2>Movimentações manuais</h2>
      <div className="ph-sub">A trilha de auditoria (tabela <code>estoque_movimentos</code> no Supabase) ainda não
        foi criada — as baixas gravam no Sienge, mas não ficam listadas aqui até a tabela existir.</div></div></div></div>
  )
  if (!movs || movs.length === 0) return null

  return (
    <div className="panel">
      <div className="phead"><div><h2>Movimentações manuais</h2>
        <div className="ph-sub">Baixas, entradas e estornos feitos pelo app. O estorno grava o movimento
          compensatório no Sienge.</div></div></div>
      {erro && <div className="es-msg es-msg-erro">{erro}</div>}
      <div className="tablewrap"><table className="data">
        <thead><tr>
          <th>Quando</th><th>Operação</th><th>Insumo</th><th className="rgt">Qtd</th>
          <th>Usuário</th><th className="rgt">Sienge</th><th className="rgt"></th>
        </tr></thead>
        <tbody>
          {movs.map((m) => {
            const ok = m.sienge_status >= 200 && m.sienge_status < 300
            const podeEstornar = ok && !m.estornado && !m.estorno_de && m.operacao !== 'estorno'
            return (
              <tr key={m.id} style={m.estornado ? { opacity: .55 } : undefined}>
                <td className="num mut">{dataFmt(m.criado_em)}</td>
                <td><span className={`es-tag es-tag-${m.operacao}`}>{m.operacao}</span>
                  {m.estornado && <span className="mut"> · estornado</span>}
                  {m.estorno_de && <span className="mut"> · de #{m.estorno_de}</span>}</td>
                <td className="ct-desc-td"><span className="ct-desc">{m.descricao}</span></td>
                <td className="rgt num">{qt(m.quantidade, m.unidade)}</td>
                <td className="mut" style={{ fontSize: 12 }}>{m.usuario}</td>
                <td className="rgt">{ok ? <span className="es-ok">✓</span> : <span className="es-err">✗ {m.sienge_status}</span>}</td>
                <td className="rgt">{podeEstornar && (
                  <button className="es-estorno" disabled={busy === m.id} onClick={() => estornar(m.id)}>
                    {busy === m.id ? '…' : 'Estornar'}</button>)}</td>
              </tr>
            )
          })}
        </tbody>
      </table></div>
    </div>
  )
}

export function Estoque({ obra, admin }: { obra: string; admin?: boolean }) {
  const [data, setData] = useState<EstoqueMaterial | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    setData(null); setErro(null)
    api.estoqueMaterial(obra).then(setData).catch((e: Error) => setErro(e.message))
  }, [obra, refreshKey])

  const recarregar = () => setRefreshKey((k) => k + 1)

  if (erro) return <div className="errbox"><b>Não foi possível carregar o estoque</b>{erro}</div>
  if (!data) return <div className="skel" style={{ height: 460 }} />
  if (!data.disponivel) {
    return (
      <div className="panel">
        <div className="phead"><div><h2>Estoque — material</h2>
          <div className="ph-sub">{data.mensagem}</div></div></div>
        <div className="empty">As movimentações de almoxarifado desta obra ainda estão sendo coletadas do Sienge.</div>
      </div>
    )
  }

  const alertas = data.alertas ?? []
  const parados = data.parados ?? []
  const st = data.resumo_status ?? { ruptura: 0, critico: 0, baixo: 0, ok: 0, parado: 0 }
  const emRisco = st.ruptura + st.critico + st.baixo

  return (
    <div style={{ display: 'grid', gap: 13 }}>
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
        <Kpi label="INSUMOS EM ESTOQUE" valor={data.n_insumos ?? 0} sub={`${st.ok} saudáveis`} />
        <Kpi label="VALOR EM ESTOQUE" valor={data.valor_em_estoque ?? 0} prefixo="R$ " sub="capital em material" />
        <Kpi label="CAPITAL PARADO" valor={data.valor_parado ?? 0} prefixo="R$ " sub={`${st.parado} insumos sem consumo`} tom={(data.valor_parado ?? 0) > 0 ? 'alerta' : undefined} />
        <Kpi label="EM RISCO" valor={emRisco} sub={`${st.ruptura} ruptura · ${st.critico} crítico`} tom={emRisco ? 'alerta' : undefined} />
      </div>

      {admin && <Movimentar obra={obra} onDone={recarregar} />}

      <div className="panel">
        <div className="phead"><div><h2>Risco de ruptura</h2>
          <div className="ph-sub">Insumos com saldo baixo ou zerado <b>e consumo ativo</b>, ordenados por impacto
            (R$ de material consumido por dia). Cobertura = saldo ÷ consumo diário recente.</div></div></div>
        {alertas.length === 0 ? (
          <div className="empty">Nenhum insumo em risco de ruptura na janela atual.</div>
        ) : (
          <div className="tablewrap"><table className="data">
            <thead><tr>
              <th>Insumo</th><th className="rgt">Prior.</th><th className="rgt">Saldo</th>
              <th className="rgt">Consumo/dia</th><th className="rgt">Cobertura</th>
              <th className="rgt">Ruptura</th><th className="rgt">Impacto/dia</th>
            </tr></thead>
            <tbody>
              {alertas.map((i) => (
                <tr key={i.resource_id}>
                  <td className="ct-desc-td"><span className="ct-desc">{i.descricao}</span></td>
                  <td className="rgt"><span className={`es-prio es-${i.status}`}>{i.prioridade}</span></td>
                  <td className="rgt num">{qt(i.saldo, i.unidade)}</td>
                  <td className="rgt num mut">{qt(i.consumo_dia, i.unidade)}</td>
                  <td className="rgt"><Cobertura i={i} /></td>
                  <td className="rgt num mut">{dataFmt(i.data_ruptura)}</td>
                  <td className="rgt"><b className="num">{rs(i.impacto_dia)}</b></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>

      <div className="panel">
        <div className="phead"><div><h2>Capital parado — estoque sem giro</h2>
          <div className="ph-sub">Saldo relevante sem consumo recente. Dinheiro empatado em material que pode ser
            redistribuído, devolvido ou renegociado.</div></div></div>
        {parados.length === 0 ? (
          <div className="empty">Nenhum estoque parado relevante.</div>
        ) : (
          <div className="tablewrap"><table className="data">
            <thead><tr>
              <th>Insumo</th><th className="rgt">Saldo</th>
              <th className="rgt">Sem consumo</th><th className="rgt">Capital parado</th>
            </tr></thead>
            <tbody>
              {parados.map((i) => (
                <tr key={i.resource_id}>
                  <td className="ct-desc-td"><span className="ct-desc">{i.descricao}</span></td>
                  <td className="rgt num mut">{qt(i.saldo, i.unidade)}</td>
                  <td className="rgt num mut">{i.dias_sem_consumo != null ? `${i.dias_sem_consumo} dias` : 'nunca'}</td>
                  <td className="rgt"><b className="num">{rs(i.valor_saldo)}</b></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>

      {admin && <Historico obra={obra} refreshKey={refreshKey} onDone={recarregar} />}

      {(data.unidades_inconsistentes ?? 0) > 0 && (
        <div className="ph-sub" style={{ paddingLeft: 4 }}>
          ⚠ {data.unidades_inconsistentes} insumo(s) com unidade base inconsistente — qualidade de dado a revisar.
        </div>
      )}
      <div className="ph-sub" style={{ paddingLeft: 4, opacity: .7 }}>
        Fonte: movimentações de almoxarifado do Sienge · saldo = entradas − saídas · {STATUS_ROT.ok} = giro normal.
        {data.coletado_em && ` Coletado em ${dataFmt(data.coletado_em.slice(0, 10))}.`}
      </div>
    </div>
  )
}
