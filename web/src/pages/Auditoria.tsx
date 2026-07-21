import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useState } from 'react'
import {
  baixarRelatorioAuditoria,
  type Auditoria as AuditoriaData, type Formato, type Periodo,
} from '../lib/api'
import { CountUp } from '../components/CountUp'

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
const rotuloMes = (iso: string) => {
  const d = new Date(iso + 'T00:00:00')
  return `${MESES[d.getMonth()]}/${String(d.getFullYear()).slice(2)}`
}

const PERIODOS: Array<{ id: Periodo; label: string }> = [
  { id: 'Mes', label: 'Mês' },
  { id: 'Trimestre', label: 'Trimestre' },
  { id: 'Semestre', label: 'Semestre' },
  { id: 'Anual', label: 'Ano' },
  { id: 'Tudo', label: 'Tudo' },
]

const eixo = { fill: 'var(--faint)', fontSize: 10, fontFamily: 'var(--mono)' }

function Card({ label, valor, sub, tom }: {
  label: string; valor: number; sub?: string; tom?: 'alerta'
}) {
  return (
    <div className="kpi">
      <div className="lbl"><span className={tom ? 'tag red' : 'tag'} />{label}</div>
      <div className="val num" style={tom ? { color: 'var(--accent-ink)' } : undefined}>
        <CountUp value={valor} />
      </div>
      {sub && <div className="foot"><span className="delta">{sub}</span></div>}
    </div>
  )
}

export function Auditoria({
  data, obra, periodo, obras, onObra, onPeriodo,
}: {
  data: AuditoriaData
  obra: string
  periodo: Periodo
  obras: string[]
  onObra: (o: string) => void
  onPeriodo: (p: Periodo) => void
}) {
  const k = data.kpis
  const serie = data.serie.map((s) => ({ ...s, label: rotuloMes(s.mes) }))
  const comp = data.comparativo.map((c) => ({ ...c, label: rotuloMes(c.mes) }))
  const agingMax = Math.max(1, ...data.aging.map((a) => a.qtd))
  const maxPend = Math.max(1, ...data.top_pendentes.map((m) => m.pendentes))

  const fmtData = (iso: string) =>
    new Date(iso + 'T00:00:00').toLocaleDateString('pt-BR')

  const [baixando, setBaixando] = useState<Formato | null>(null)
  const [erroExport, setErroExport] = useState<string | null>(null)

  async function exportar(formato: Formato) {
    setErroExport(null)
    setBaixando(formato)
    try {
      await baixarRelatorioAuditoria(obra, periodo, formato)
    } catch (e) {
      setErroExport((e as Error).message)
    } finally {
      setBaixando(null)
    }
  }

  return (
    <>
      <div className="pagehead reveal">
        <div>
          <div className="eyebrow">{data.obra}</div>
          <h1>Auditoria gerencial</h1>
          <div className="sub">
            Indicadores históricos de FVS e não-conformidades ·{' '}
            {fmtData(data.intervalo.de)} a {fmtData(data.intervalo.ate)}
          </div>
        </div>
        <div className="headmeta" style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => exportar('excel')} disabled={baixando !== null}>
            <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
            </svg>
            {baixando === 'excel' ? 'Gerando…' : 'Excel'}
          </button>
          <button className="btn primary" onClick={() => exportar('pdf')} disabled={baixando !== null}>
            <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
            </svg>
            {baixando === 'pdf' ? 'Gerando…' : 'PDF executivo'}
          </button>
        </div>
      </div>

      {erroExport && <div className="errbox" style={{ marginBottom: 13 }}>{erroExport}</div>}

      <div className="filters reveal" style={{ animationDelay: '.05s' }}>
        <div className="field">
          <label htmlFor="a-obra">Obra</label>
          <select id="a-obra" value={obra} onChange={(e) => onObra(e.target.value)}>
            <option value="">Todas as obras</option>
            {obras.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Período</label>
          <div className="segmented">
            {PERIODOS.map((p) => (
              <button
                key={p.id}
                className={periodo === p.id ? 'on' : ''}
                onClick={() => onPeriodo(p.id)}
                aria-pressed={periodo === p.id}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="secao-lbl">Indicadores do período</div>
      <section className="kpis">
        <Card label="Inspeções" valor={k.total_insp} sub="no período" />
        <Card label="Finalizadas" valor={k.finalizada} sub={`${k.pct_finalizada.toFixed(0)}% do total`} />
        <Card label="Em andamento" valor={k.em_andamento} />
        <Card label="NC no período" valor={k.nc_total} />
        <Card
          label="Não iniciadas"
          valor={k.snap_nao_iniciada}
          sub={k.snap_criticas > 0 ? `${k.snap_criticas} há mais de 7 dias` : 'estado atual'}
          tom={k.snap_nao_iniciada > 0 ? 'alerta' : undefined}
        />
      </section>

      <section className="bento">
        <div className="panel reveal" style={{ animationDelay: '.12s' }}>
          <div className="phead">
            <div>
              <h2>Evolução mensal</h2>
              <div className="ph-sub">inspeções agrupadas pelo mês de execução</div>
            </div>
          </div>
          {serie.length > 0 ? (
            <div style={{ width: '100%', height: 250, marginTop: 12 }}>
              <ResponsiveContainer>
                <LineChart data={serie} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="var(--hairline)" vertical={false} />
                  <XAxis dataKey="label" tick={eixo} tickLine={false}
                         axisLine={{ stroke: 'var(--hairline)' }} minTickGap={20} />
                  <YAxis tick={eixo} tickLine={false} axisLine={false} width={44} />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--surface)', border: '1px solid var(--hairline-2)',
                      borderRadius: 10, fontSize: 12.5,
                    }}
                    labelStyle={{ color: 'var(--faint)', fontFamily: 'var(--mono)', fontSize: 11 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11.5, fontFamily: 'var(--mono)' }} />
                  <Line type="monotone" dataKey="finalizada" name="finalizadas"
                        stroke="var(--done)" strokeWidth={2.2} dot={false} />
                  <Line type="monotone" dataKey="em_andamento" name="em andamento"
                        stroke="var(--prog)" strokeWidth={2.2} dot={false} />
                  <Line type="monotone" dataKey="nc_total" name="NC"
                        stroke="var(--accent)" strokeWidth={2} strokeDasharray="4 3" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="empty">Sem inspeções no período.</div>}
        </div>

        <div className="panel reveal" style={{ animationDelay: '.18s' }}>
          <div className="phead">
            <div>
              <h2>Aging do backlog</h2>
              <div className="ph-sub">tempo sem abertura no inmeta</div>
            </div>
          </div>
          {data.aging.some((a) => a.qtd > 0) ? (
            <>
              <div className="aging">
                {data.aging.map((a) => {
                  const crit = a.faixa === '8-14d' || a.faixa === '>14d'
                  return (
                    <div className="agrow" key={a.faixa}>
                      <span className="ak">{a.faixa}</span>
                      <span className="bar">
                        <i style={{
                          width: `${(a.qtd / agingMax) * 100}%`,
                          background: crit ? 'var(--accent)' : 'var(--prog)',
                        }} />
                      </span>
                      <span className={crit && a.qtd > 0 ? 'av crit num' : 'av num'}>{a.qtd}</span>
                    </div>
                  )
                })}
              </div>
              <div className="nc-split">
                <div>
                  <div className="v num">{data.sla.media_dias.toFixed(0)}</div>
                  <div className="k">dias em média</div>
                </div>
                <div>
                  <div className="v num">{data.sla.max_dias}</div>
                  <div className="k">máximo</div>
                </div>
              </div>
            </>
          ) : <div className="empty">Snapshots ainda não disponíveis.</div>}
        </div>
      </section>

      <section className="lower">
        <div className="panel reveal" style={{ animationDelay: '.14s' }}>
          <div className="phead">
            <div>
              <h2>Comparativo entre obras</h2>
              <div className="ph-sub">fvs finalizadas por mês</div>
            </div>
          </div>
          {comp.length > 0 ? (
            <div style={{ width: '100%', height: 230, marginTop: 12 }}>
              <ResponsiveContainer>
                <BarChart data={comp} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="var(--hairline)" vertical={false} />
                  <XAxis dataKey="label" tick={eixo} tickLine={false}
                         axisLine={{ stroke: 'var(--hairline)' }} minTickGap={20} />
                  <YAxis tick={eixo} tickLine={false} axisLine={false} width={44} />
                  <Tooltip
                    cursor={{ fill: 'var(--surface-2)' }}
                    contentStyle={{
                      background: 'var(--surface)', border: '1px solid var(--hairline-2)',
                      borderRadius: 10, fontSize: 12.5,
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11.5, fontFamily: 'var(--mono)' }} />
                  <Bar dataKey="cape_town" name="Cape Town" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="holmes" name="Holmes" fill="var(--prog)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="empty">Sem dados para comparar.</div>}
        </div>

        <div className="panel reveal" style={{ animationDelay: '.2s' }}>
          <div className="phead">
            <div>
              <h2>Modelos com mais pendências</h2>
              <div className="ph-sub">estado atual · todas as obras selecionadas</div>
            </div>
          </div>
          {data.top_pendentes.length > 0 ? (
            <div className="rank">
              {data.top_pendentes.map((m, i) => (
                <div className="rrow" key={m.modelo}>
                  <span className="rk num">{String(i + 1).padStart(2, '0')}</span>
                  <span className="rn" title={m.modelo}>{m.modelo}</span>
                  <span className="bar">
                    <i style={{
                      width: `${(m.pendentes / maxPend) * 100}%`,
                      background: m.nc > 0 ? 'var(--accent)' : 'var(--prog)',
                    }} />
                  </span>
                  <span className="rv num">{m.pendentes}</span>
                </div>
              ))}
            </div>
          ) : <div className="empty">Nenhuma pendência registrada.</div>}
        </div>
      </section>

      <section className="panel reveal" style={{ animationDelay: '.16s' }}>
        <div className="phead">
          <div>
            <h2>Alertas críticos</h2>
            <div className="ph-sub">não iniciadas há mais de 7 dias</div>
          </div>
        </div>

        {data.criticas.length > 0 ? (
          <>
            <div className="banner" style={{ marginTop: 12 }}>
              <svg className="ic" width="20" height="20" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="2">
                <path d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
              </svg>
              <div>
                <div className="bt">
                  {data.criticas.length} FVS aguardando abertura há mais de 7 dias
                </div>
                <div className="bs">Requerem abertura imediata no InMeta.</div>
              </div>
            </div>
            <div className="tablewrap">
              <table className="data">
                <colgroup>
                  <col style={{ width: '18%' }} /><col style={{ width: '16%' }} />
                  <col style={{ width: '30%' }} /><col style={{ width: '22%' }} />
                  <col style={{ width: '9%' }} /><col style={{ width: '5%' }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>Obra</th><th>Pavimento</th><th>Modelo FVS</th><th>Local</th>
                    <th className="rgt">Dias</th><th className="rgt">NC</th>
                  </tr>
                </thead>
                <tbody>
                  {data.criticas.map((c, i) => (
                    <tr key={`${c.modelo}-${c.pavimento}-${i}`}>
                      <td><span className="trunc mut">{c.obra}</span></td>
                      <td><span className="trunc">{c.pavimento}</span></td>
                      <td><span className="trunc" title={c.modelo}>{c.modelo}</span></td>
                      <td><span className="trunc mut" title={c.local}>{c.local}</span></td>
                      <td className="rgt"><span className="ncbadge">{c.dias_pendente}</span></td>
                      <td className="rgt">
                        {c.nc > 0 ? <span className="ncbadge">{c.nc}</span>
                                  : <span className="num mut">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="okbanner" style={{ marginTop: 12, marginBottom: 0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            Nenhum alerta crítico no momento.
          </div>
        )}
      </section>

      <div className="foot-note">
        <span className="chip">{data.dias_snapshot} dias de snapshot</span>
        Séries mensais vêm das inspeções do InMeta; aging e alertas, dos snapshots diários.
      </div>
    </>
  )
}
