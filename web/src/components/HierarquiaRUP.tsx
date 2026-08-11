import { Fragment, useEffect, useState } from 'react'
import { api, type RupCelula, type RupHierarquia, type RupStatus } from '../lib/api'

const fmt = (n: number) => n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })
const fmt2 = (n: number) => n.toLocaleString('pt-BR', { maximumFractionDigits: 2 })
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

const STATUS: Record<RupStatus, { rotulo: string; cls: string }> = {
  dentro:  { rotulo: 'dentro da faixa', cls: 'st-ok' },
  acima:   { rotulo: 'acima', cls: 'st-alto' },
  abaixo:  { rotulo: 'abaixo', cls: 'st-baixo' },
  sem_rup: { rotulo: 'sem produção', cls: 'st-cinza' },
  sem_ref: { rotulo: 'sem referência', cls: 'st-cinza' },
}

/** Barra da faixa mín–máx do parceiro com o marcador da nossa RUP. */
function Faixa({ rup, banda, status }: {
  rup: number | null; banda: RupCelula['banda']; status: RupStatus
}) {
  if (!banda || rup == null) return <span className="mut" style={{ fontSize: 12 }}>—</span>
  const esc = Math.max(banda.max, rup) * 1.12
  const pct = (v: number) => `${Math.min(100, (v / esc) * 100)}%`
  const cor = status === 'dentro' ? 'var(--ok)' : status === 'acima' ? 'var(--accent)' : '#c99a00'
  return (
    <div className="hr-faixa" title={`faixa ${banda.min}–${banda.max} · nossa ${fmt2(rup)}`}>
      <div className="hr-band" style={{ left: pct(banda.min), width: `calc(${pct(banda.max)} - ${pct(banda.min)})` }} />
      {banda.med != null && <div className="hr-med" style={{ left: pct(banda.med) }} />}
      <div className="hr-marca" style={{ left: pct(rup), background: cor }} />
    </div>
  )
}

export function HierarquiaRUP({ obra }: { obra: string }) {
  const [data, setData] = useState<RupHierarquia | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [aberta, setAberta] = useState<string | null>(null)

  useEffect(() => {
    setData(null); setErro(null); setAberta(null)
    api.rupHierarquia(obra).then(setData).catch((e: Error) => setErro(e.message))
  }, [obra])

  if (erro) return <div className="errbox"><b>Não foi possível carregar a produtividade</b>{erro}</div>
  if (!data) return <div className="skel" style={{ height: 460 }} />

  const r = data.resumo
  return (
    <div className="panel">
      <div className="phead">
        <div>
          <h2>Produtividade por célula construtiva</h2>
          <div className="ph-sub">
            RUP real (HH ÷ produção executada) consolidada por célula, contra a faixa de
            referência do parceiro. {r.dentro_faixa} de {r.com_rup} células com RUP estão
            dentro da faixa.
            {r.fonte_hh === 'sugerido' && ' HH atribuído por sugestão — confirme na aba Amarração para travar.'}
          </div>
        </div>
      </div>

      <div className="tablewrap">
        <table className="data hr-tbl">
          <thead>
            <tr>
              <th>Célula construtiva</th>
              <th className="rgt">HH</th>
              <th className="rgt">Produção</th>
              <th className="rgt">RUP real</th>
              <th>Faixa do parceiro</th>
              <th>Situação</th>
            </tr>
          </thead>
          <tbody>
            {data.celulas.map((c) => {
              const st = STATUS[c.status]
              const aberto = aberta === c.celula
              const temPacotes = c.pacotes.some((p) => p.producao > 0 || p.hh > 0)
              return (
                <Fragment key={c.celula}>
                  <tr className="hr-cel" onClick={() => temPacotes && setAberta(aberto ? null : c.celula)}
                      style={{ cursor: temPacotes ? 'pointer' : 'default' }}>
                    <td>
                      <span className="hr-caret">{temPacotes ? (aberto ? '▾' : '▸') : ''}</span>
                      <b>{cap(c.celula)}</b>
                      {c.unidades_mistas && <span className="hr-mix" title="a célula tem pacotes de unidades diferentes; a RUP é da unidade dominante">un. mistas</span>}
                    </td>
                    <td className="rgt"><span className="num mut">{fmt(c.hh)}</span></td>
                    <td className="rgt"><span className="num mut">{c.producao ? `${fmt(c.producao)} ${c.unidade}` : '—'}</span></td>
                    <td className="rgt"><b className="num">{c.rup != null ? fmt2(c.rup) : '—'}</b></td>
                    <td><Faixa rup={c.rup} banda={c.banda} status={c.status} /></td>
                    <td><span className={`hr-badge ${st.cls}`}>{st.rotulo}</span></td>
                  </tr>
                  {aberto && c.pacotes.filter((p) => p.producao > 0 || p.hh > 0).map((p, i) => (
                    <tr key={`${c.celula}-${i}`} className="hr-pac">
                      <td><span className="hr-pac-nome">{p.pacote}</span>{p.n_lotes > 1 && <span className="hr-lotes">{p.n_lotes} lotes</span>}</td>
                      <td className="rgt"><span className="num mut">{fmt(p.hh)}</span></td>
                      <td className="rgt"><span className="num mut">{p.producao ? `${fmt(p.producao)} ${p.unidade}` : '—'}</span></td>
                      <td className="rgt"><span className="num">{p.rup != null ? fmt2(p.rup) : '—'}</span></td>
                      <td colSpan={2}>
                        {p.rup == null && p.producao > 0 && <span className="mut" style={{ fontSize: 12 }}>HH não atribuído a este pacote — confirme na Amarração</span>}
                      </td>
                    </tr>
                  ))}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
