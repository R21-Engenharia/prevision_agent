import { Fragment, useEffect, useMemo, useState } from 'react'
import { api, type Rup, type RupFvs } from '../lib/api'
import { CountUp } from '../components/CountUp'
import { DeparaEAP } from '../components/DeparaEAP'
import { HierarquiaRUP } from '../components/HierarquiaRUP'

const fmt = (n: number) => n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })
const fmt1 = (n: number) => n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })

function limpaNome(r: RupFvs): string {
  return r.fvs_nome.replace(/^FVS\s+[\d.]+\s*-\s*/, '').trim() || r.fvs_codigo
}

function funcaoDominante(r: RupFvs): string {
  const e = Object.entries(r.hh_por_funcao || {})
  if (!e.length) return '—'
  return e.sort((a, b) => b[1] - a[1])[0][0]
}

function Kpi({ label, valor, sufixo, sub, tom }: {
  label: string; valor: number; sufixo?: string; sub?: string; tom?: 'alerta'
}) {
  return (
    <div className="kpi">
      <div className="lbl"><span className={tom ? 'tag red' : 'tag'} />{label}</div>
      <div className="val num" style={tom ? { color: 'var(--accent-ink)' } : undefined}>
        <CountUp value={valor} />{sufixo}
      </div>
      {sub && <div className="foot"><span className="delta">{sub}</span></div>}
    </div>
  )
}

export function MaoDeObra({ obra, admin }: { obra: string; admin: boolean }) {
  const [aba, setAba] = useState<'prod' | 'hh' | 'depara'>('prod')
  const [data, setData] = useState<Rup | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [aberta, setAberta] = useState<string | null>(null)

  useEffect(() => {
    if (!obra) return
    setData(null); setErro(null); setAberta(null)
    api.rup(obra).then(setData).catch((e: Error) => setErro(e.message))
  }, [obra])

  const maxHh = useMemo(
    () => Math.max(1, ...(data?.fvs ?? []).map((r) => r.hh_total)),
    [data],
  )

  const tabs = (
    <div className="rup-tabs">
      <button className={aba === 'prod' ? 'on' : ''} onClick={() => setAba('prod')}>
        Produtividade
      </button>
      <button className={aba === 'hh' ? 'on' : ''} onClick={() => setAba('hh')}>
        Mão de obra real
      </button>
      <button className={aba === 'depara' ? 'on' : ''} onClick={() => setAba('depara')}>
        Amarração EAP (Sienge)
      </button>
    </div>
  )

  if (aba === 'prod') {
    return (
      <div style={{ display: 'grid', gap: 13 }}>
        {tabs}
        <HierarquiaRUP obra={obra} />
      </div>
    )
  }
  if (aba === 'depara') {
    return (
      <div style={{ display: 'grid', gap: 13 }}>
        {tabs}
        <DeparaEAP obra={obra} admin={admin} />
      </div>
    )
  }

  if (erro) {
    return (
      <div style={{ display: 'grid', gap: 13 }}>
        {tabs}
        <div className="errbox"><b>Não foi possível carregar a mão de obra</b>{erro}</div>
      </div>
    )
  }
  if (!data) {
    return (
      <div style={{ display: 'grid', gap: 13 }}>
        {tabs}
        <div className="skel" style={{ height: 92 }} />
        <div className="skel" style={{ height: 400 }} />
      </div>
    )
  }

  const r = data.resumo

  return (
    <div style={{ display: 'grid', gap: 13 }}>
      {tabs}
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
        <Kpi label="SERVIÇOS (FVS)" valor={r.fvs} sub="controlados no RDO" />
        <Kpi label="Hh REAL ACUMULADO" valor={r.hh_total} sufixo=" h" sub="efetivo × 8,8h/dia" />
        <Kpi label="COM RUP" valor={r.com_rup} sub="denominador amarrado" />
        <Kpi label="AGUARDANDO SIENGE" valor={r.aguardando_sienge} tom="alerta"
             sub="falta quantidade executada" />
      </div>

      <div className="panel">
        <div className="phead">
          <div>
            <h2>Mão de obra real por serviço</h2>
            <div className="ph-sub">
              Hh sai do efetivo lançado no RDO (premissa de 8,8h/dia por colaborador).
              A RUP (Hh ÷ quantidade executada) entra quando o Sienge trouxer a
              quantidade — até lá o sistema não inventa o número.
            </div>
          </div>
        </div>

        {data.fvs.length === 0 ? (
          <div className="empty">Nenhum serviço com efetivo no RDO para esta obra.</div>
        ) : (
          <div className="tablewrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Serviço (FVS)</th>
                  <th className="rgt">Hh real</th>
                  <th className="rgt">Dias</th>
                  <th className="rgt">Efet./dia</th>
                  <th className="rgt">Pav.</th>
                  <th>Função principal</th>
                  <th className="rgt">RUP</th>
                </tr>
              </thead>
              <tbody>
                {data.fvs.map((f) => {
                  const aberto = aberta === f.fvs_codigo
                  const obsoleto = /obsolet/i.test(f.fvs_nome)
                  return (
                    <Fragment key={f.fvs_codigo}>
                      <tr onClick={() => setAberta(aberto ? null : f.fvs_codigo)}
                          style={{ cursor: 'pointer' }}>
                        <td>
                          <div className="rup-serv">
                            <span className="num mut" style={{ minWidth: 62, display: 'inline-block' }}>
                              {f.fvs_codigo}
                            </span>
                            <span className="trunc" title={limpaNome(f)}>{limpaNome(f)}</span>
                            {obsoleto && <span className="pill" style={{ opacity: .6 }}>obsoleto</span>}
                          </div>
                          <div className="rup-bar">
                            <span style={{ width: `${(f.hh_total / maxHh) * 100}%` }} />
                          </div>
                        </td>
                        <td className="rgt"><b className="num">{fmt(f.hh_total)}</b></td>
                        <td className="rgt"><span className="num mut">{f.dias_trabalhados}</span></td>
                        <td className="rgt"><span className="num mut">{fmt1(f.efetivo_medio_dia)}</span></td>
                        <td className="rgt"><span className="num mut">{f.n_pavimentos}</span></td>
                        <td><span className="trunc">{funcaoDominante(f)}</span></td>
                        <td className="rgt">
                          {f.rup_real != null
                            ? <b className="num">{fmt1(f.rup_real)} <span className="mut">Hh/{f.unidade}</span></b>
                            : <span className="mut" title="Falta a quantidade executada (Sienge)">— aguardando</span>}
                        </td>
                      </tr>
                      {aberto && (
                        <tr className="rup-det">
                          <td colSpan={7}>
                            <div className="rup-det-grid">
                              <div>
                                <div className="rup-det-lbl">Hh por função</div>
                                <div className="rup-funcs">
                                  {Object.entries(f.hh_por_funcao)
                                    .sort((a, b) => b[1] - a[1])
                                    .map(([fn, hh]) => (
                                      <span className="chip" key={fn}>
                                        {fn} <b className="num">{fmt(hh)}h</b>
                                      </span>
                                    ))}
                                </div>
                              </div>
                              <div>
                                <div className="rup-det-lbl">
                                  Confiança da amostra
                                </div>
                                <div className="mut" style={{ fontSize: 12 }}>
                                  {f.pct_compartilhado > 40
                                    ? `Efetivo compartilhado em ${fmt1(f.pct_compartilhado)}% dos registros — Hh menos preciso para este serviço.`
                                    : `Efetivo dedicado (${fmt1(f.pct_compartilhado)}% compartilhado) — amostra confiável.`}
                                </div>
                                {f.pavimentos?.length > 0 && (
                                  <div className="mut" style={{ fontSize: 12, marginTop: 6 }}>
                                    {f.pavimentos.length} pavimento(s): {f.pavimentos.slice(0, 6).join(' · ')}
                                    {f.pavimentos.length > 6 ? ' …' : ''}
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
