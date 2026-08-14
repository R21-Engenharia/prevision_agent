import { type ReactNode, useEffect, useState } from 'react'
import { api, type CustoDesembolso, type CustoItem, type CustoMaterial, type RupJanela } from '../lib/api'
import { CountUp } from '../components/CountUp'

const JANELAS: { id: RupJanela; rot: string }[] = [
  { id: 'mes_atual', rot: 'Mês atual' },
  { id: 'mes_anterior', rot: 'Mês anterior' },
  { id: '6m', rot: '6 meses' },
  { id: '12m', rot: '12 meses' },
  { id: 'obra', rot: 'Obra inteira' },
]

const JAN_ROT: Record<string, string> = { '7d': '7 dias', '15d': '15 dias', '30d': '30 dias', '60d': '60 dias', '90d': '90 dias' }

/** Painel executivo de previsão de desembolso (parcelas com vencimento real). */
function Desembolso({ obra }: { obra: string }) {
  const [d, setD] = useState<CustoDesembolso | null>(null)
  useEffect(() => { setD(null); api.custosDesembolso(obra).then(setD).catch(() => setD(null)) }, [obra])
  if (!d || !d.disponivel) return null
  const brl = (n: number) => `R$ ${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
  return (
    <div className="panel">
      <div className="phead"><div><h2>Previsão de desembolso (comprometido)</h2>
        <div className="ph-sub">Parcelas a pagar com vencimento real no Sienge. Total a pagar {brl(d.total_a_pagar ?? 0)}
          {(d.vencidas ?? 0) > 0 && <> · <b style={{ color: 'var(--accent-ink)' }}>{brl(d.vencidas ?? 0)} vencidas</b></>}.</div></div></div>
      <div className="ct-janelas">
        {Object.entries(d.janelas ?? {}).map(([k, v]) => (
          <div className="ct-jan" key={k}>
            <div className="ct-jan-rot">próximos {JAN_ROT[k] ?? k}</div>
            <div className="ct-jan-val num">{brl(v)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

const rs = (n: number) => `R$ ${n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
const rs2 = (n: number) => `R$ ${n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function Kpi({ label, valor, sufixo, prefixo, sub, tom }: {
  label: string; valor: number; sufixo?: string; prefixo?: string; sub?: string; tom?: 'alerta'
}) {
  return (
    <div className="kpi">
      <div className="lbl"><span className={tom ? 'tag red' : 'tag'} />{label}</div>
      <div className="val num" style={tom ? { color: 'var(--accent-ink)' } : undefined}>
        {prefixo}<CountUp value={valor} />{sufixo}
      </div>
      {sub && <div className="foot"><span className="delta">{sub}</span></div>}
    </div>
  )
}

/** Tendência: último preço vs média histórica (▲ pior/vermelho, ▼ melhor/verde).
 *  Tooltip traz último, média e 1ª compra — a referência é sempre o histórico. */
function Tend({ t }: { t: CustoItem['tendencia'] }) {
  if (t.variacao_pct == null) return <span className="mut">—</span>
  const dica = `último R$ ${t.ultimo} · média R$ ${t.medio} · 1ª compra R$ ${t.primeira} · vs 1ª ${t.variacao_primeira_pct}% · ${t.n_compras} compras`
  if (t.direcao === 'estavel') return <span className="mut" title={dica}>estável</span>
  const alta = t.direcao === 'alta'
  return (
    <span className={`ct-tend ${alta ? 'ct-alta' : 'ct-baixa'}`} title={dica}>
      {alta ? '▲' : '▼'} {Math.abs(t.variacao_pct)}%{t.acelerando ? ' ⚡' : ''}
      {t.variacao_primeira_pct != null && <span className="ct-vs1 mut"> ({t.variacao_primeira_pct > 0 ? '+' : ''}{t.variacao_primeira_pct}% vs 1ª)</span>}
    </span>
  )
}

const CLS: Record<string, string> = { A: 'ct-a', B: 'ct-b', C: 'ct-c' }

export function Custos({ obra }: { obra: string }) {
  const [data, setData] = useState<CustoMaterial | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [janela, setJanela] = useState<RupJanela>('obra')

  useEffect(() => {
    setData(null); setErro(null)
    api.custosMaterial(obra, janela).then(setData).catch((e: Error) => setErro(e.message))
  }, [obra, janela])

  const seletor = (
    <div className="hr-janelas">
      <span className="hr-jan-lbl">Período das compras:</span>
      {JANELAS.map((j) => (
        <button key={j.id} className={janela === j.id ? 'on' : ''} onClick={() => setJanela(j.id)}>{j.rot}</button>
      ))}
    </div>
  )
  const envolver = (conteudo: ReactNode) => (
    <div style={{ display: 'grid', gap: 13 }}>{seletor}{conteudo}</div>
  )

  if (erro) return envolver(<div className="errbox"><b>Não foi possível carregar os custos</b>{erro}</div>)
  if (!data) return envolver(<div className="skel" style={{ height: 460 }} />)

  if (!data.disponivel) {
    return envolver(
      <div className="panel">
        <div className="phead"><div><h2>Inteligência de custos — material</h2>
          <div className="ph-sub">{data.mensagem}</div></div></div>
        <div className="empty">As compras desta obra ainda estão sendo coletadas do Sienge.</div>
      </div>
    )
  }

  const itens = data.itens ?? []
  const alertas = data.alertas ?? []
  const abc = data.abc_resumo ?? { A: 0, B: 0, C: 0 }
  const janelaObra = (data.janela ?? 'obra') === 'obra'

  return (
    <div style={{ display: 'grid', gap: 13 }}>
      {seletor}
      {janelaObra && <Desembolso obra={obra} />}
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
        <Kpi label="TOTAL COMPRADO" valor={data.total_comprado ?? 0} prefixo="R$ " sub="material (pedidos de compra)" />
        <Kpi label="INSUMOS" valor={data.n_insumos ?? 0} sub={`${abc.A} classe A · ${abc.B} B`} />
        <Kpi label="ALERTAS DE PREÇO" valor={alertas.length} tom={alertas.length ? 'alerta' : undefined} sub="itens de peso em alta" />
        <Kpi label="CONCENTRAÇÃO (A)" valor={abc.A} sub="itens = 80% do gasto" />
      </div>

      {alertas.length > 0 && (
        <div className="panel">
          <div className="phead"><div><h2>Alertas de preço</h2>
            <div className="ph-sub">Insumos de peso (A/B) com preço subindo nas últimas compras. ⚡ = acelerando.</div></div></div>
          <div className="ct-alertas">
            {alertas.map((a) => (
              <div className={`ct-alerta ${a.nivel === 'alto' ? 'ct-alerta-alto' : ''}`} key={a.resource_id}>
                <span className={`ct-prio ct-${a.prioridade}`}>{a.prioridade}</span>
                <span className="ct-alerta-txt">{a.texto}</span>
                <span className="num mut">{rs(a.valor)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(data.grupos?.length ?? 0) > 0 && (
        <div className="panel">
          <div className="phead"><div><h2>Por grupo econômico</h2>
            <div className="ph-sub">Insumos normalizados em famílias (Concreto, Aço...). Onde o material concentra o gasto.</div></div></div>
          <div className="ct-grupos">
            {data.grupos!.slice(0, 10).map((g) => (
              <div className="ct-grp" key={g.grupo}>
                <div className="ct-grp-top">
                  <span className={`ct-cls ${CLS[g.classe]}`}>{g.classe}</span>
                  <span className="ct-grp-nome">{g.grupo}</span>
                  <span className="num ct-grp-val">{rs(g.total_valor)}</span>
                  <span className="mut ct-grp-pct">{g.pct}%</span>
                </div>
                <div className="ct-grp-bar"><span style={{ width: `${Math.min(100, g.pct)}%` }} /></div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <div className="phead"><div><h2>Curva ABC — onde o dinheiro foi</h2>
          <div className="ph-sub">Insumos ordenados por valor comprado. A = 80% do gasto, B = próximos 15%, C = resto.</div></div></div>
        <div className="tablewrap">
          <table className="data">
            <thead><tr>
              <th>Insumo</th><th className="rgt">Classe</th><th className="rgt">Comprado</th>
              <th className="rgt">% acum</th><th className="rgt">Último / médio</th>
              <th className="rgt">Compras</th><th>Tendência (vs média)</th>
            </tr></thead>
            <tbody>
              {itens.map((i) => (
                <tr key={i.resource_id}>
                  <td className="ct-desc-td"><span className="ct-desc">{i.descricao}</span>
                    <span className="ct-un mut"> · {i.unidade}</span></td>
                  <td className="rgt"><span className={`ct-cls ${CLS[i.classe]}`}>{i.classe}</span></td>
                  <td className="rgt"><b className="num">{rs(i.total_valor)}</b></td>
                  <td className="rgt"><span className="num">{rs2(i.tendencia.ultimo ?? i.preco.ultimo)}</span>
                    <span className="num mut" style={{ fontSize: 11 }}> / {rs2(i.tendencia.medio ?? i.preco.medio_ponderado)}</span></td>
                  <td className="rgt"><span className="num mut">{i.n_compras}</span></td>
                  <td><Tend t={i.tendencia} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
