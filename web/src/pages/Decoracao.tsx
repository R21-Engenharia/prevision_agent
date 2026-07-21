import type { Decoracao as DecoracaoData } from '../lib/api'
import { CountUp } from '../components/CountUp'
import { Gantt } from '../components/Gantt'

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

export function Decoracao({
  data, obra, disciplina, status, obras, onObra, onDisciplina, onStatus,
}: {
  data: DecoracaoData
  obra: string
  disciplina: string
  status: string
  obras: string[]
  onObra: (v: string) => void
  onDisciplina: (v: string) => void
  onStatus: (v: string) => void
}) {
  const k = data.kpis
  const maxPav = Math.max(1, ...data.pavimentos.map((p) => p.pct))
  const totalDisc = data.disciplinas.reduce((s, d) => s + d.total, 0)

  const filtros = (
    <div className="filters reveal" style={{ animationDelay: '.05s' }}>
      <div className="field">
        <label htmlFor="d-obra">Obra</label>
        <select id="d-obra" value={obra} onChange={(e) => onObra(e.target.value)}>
          <option value="">Todas as obras</option>
          {obras.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="d-disc">Disciplina</label>
        <select id="d-disc" value={disciplina} onChange={(e) => onDisciplina(e.target.value)}>
          <option value="">Todas</option>
          {data.facetas.disciplinas.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="d-status">Status</label>
        <select id="d-status" value={status} onChange={(e) => onStatus(e.target.value)}>
          <option value="">Todos</option>
          {data.facetas.status.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {(obra || disciplina || status) && (
        <button className="clear" onClick={() => { onObra(''); onDisciplina(''); onStatus('') }}>
          Limpar filtros
        </button>
      )}
    </div>
  )

  const cabecalho = (
    <div className="pagehead reveal">
      <div>
        <div className="eyebrow">{data.obra}</div>
        <h1>Decoração &amp; acabamentos</h1>
        <div className="sub">Cronograma executivo das atividades de acabamento.</div>
      </div>
    </div>
  )

  if (data.vazio) {
    return (
      <>
        {cabecalho}
        {filtros}
        <div className="panel"><div className="empty">
          Nenhuma atividade corresponde aos filtros selecionados.
        </div></div>
      </>
    )
  }

  return (
    <>
      {cabecalho}
      {filtros}

      <section className="kpis">
        <Kpi label="Atividades" valor={k.total} sub="no recorte" />
        <Kpi label="Finalizadas" valor={k.finalizada}
             sub={`${Math.round((k.finalizada / Math.max(k.total, 1)) * 100)}% do total`} />
        <Kpi label="Em andamento" valor={k.em_andamento} />
        <Kpi label="Avanço médio" valor={k.pct_medio} sufixo="%"
             sub={`${k.proximas_30d} iniciam em 30d`} />
        <Kpi label="Atrasadas" valor={k.atrasada}
             tom={k.atrasada > 0 ? 'alerta' : undefined}
             sub={k.atrasada > 0 ? 'prazo vencido' : 'no prazo'} />
      </section>

      <section className="panel reveal" style={{ animationDelay: '.12s' }}>
        <div className="phead">
          <div>
            <h2>Cronograma por pavimento</h2>
            <div className="ph-sub">
              {data.gantt.length} pavimentos · {data.intervalo?.de.slice(0, 4)}–{data.intervalo?.ate.slice(0, 4)}
            </div>
          </div>
        </div>
        {data.intervalo && data.gantt.length > 0 ? (
          <Gantt
            linhas={data.gantt}
            de={data.intervalo.de}
            ate={data.intervalo.ate}
            hoje={data.hoje}
          />
        ) : <div className="empty">Sem atividades para exibir.</div>}
      </section>

      <section className="lower">
        <div className="panel reveal" style={{ animationDelay: '.14s' }}>
          <div className="phead">
            <div>
              <h2>Disciplinas</h2>
              <div className="ph-sub">atividades por especialidade</div>
            </div>
          </div>
          <div className="aging" style={{ marginTop: 16 }}>
            {data.disciplinas.map((d) => {
              const pct = totalDisc > 0 ? (d.total / totalDisc) * 100 : 0
              return (
                <div key={d.disciplina}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 6 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, background: d.cor }} />
                    <span style={{ flex: 1, fontSize: 13 }}>{d.disciplina}</span>
                    <span className="num" style={{ fontSize: 13, fontWeight: 640 }}>{d.total}</span>
                    <span className="num" style={{ width: 46, textAlign: 'right', color: 'var(--faint)', fontSize: 12 }}>
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                  <div className="bar"><i style={{ width: `${pct}%`, background: d.cor }} /></div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="panel reveal" style={{ animationDelay: '.18s' }}>
          <div className="phead">
            <div>
              <h2>Avanço por pavimento</h2>
              <div className="ph-sub">primeiros {data.pavimentos.length} pavimentos</div>
            </div>
          </div>
          <div className="aging" style={{ marginTop: 16, maxHeight: 320, overflowY: 'auto' }}>
            {data.pavimentos.map((p) => (
              <div className="agrow" key={p.pavimento}>
                <span className="ak" title={p.pavimento}
                      style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {p.pavimento}
                </span>
                <span className="bar">
                  <i style={{
                    width: `${(p.pct / maxPav) * 100}%`,
                    background: p.pct >= 100 ? '#1E8E5A' : p.pct > 0 ? 'var(--prog)' : 'var(--track)',
                  }} />
                </span>
                <span className="av num">{p.pct.toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel reveal" style={{ animationDelay: '.16s' }}>
        <div className="phead">
          <div>
            <h2>Alertas</h2>
            <div className="ph-sub">deveriam ter iniciado e estão em 0%</div>
          </div>
        </div>
        {data.alertas.length > 0 ? (
          <>
            <div className="banner" style={{ marginTop: 12 }}>
              <svg className="ic" width="20" height="20" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="2">
                <path d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
              </svg>
              <div>
                <div className="bt">
                  {data.alertas.length} atividade{data.alertas.length > 1 ? 's' : ''} com início vencido
                </div>
                <div className="bs">
                  Atraso máximo: {data.alertas[0]?.dias} dias.
                </div>
              </div>
            </div>
            <div className="tablewrap">
              <table className="data">
                <colgroup>
                  <col style={{ width: '9%' }} /><col style={{ width: '20%' }} />
                  <col style={{ width: '16%' }} /><col style={{ width: '33%' }} />
                  <col style={{ width: '12%' }} /><col style={{ width: '10%' }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>WBS</th><th>Pavimento</th><th>Disciplina</th><th>Serviço</th>
                    <th className="rgt">Início</th><th className="rgt">Atraso</th>
                  </tr>
                </thead>
                <tbody>
                  {data.alertas.map((a, i) => (
                    <tr key={`${a.wbs}-${i}`}>
                      <td><span className="num mut">{a.wbs}</span></td>
                      <td><span className="trunc" title={a.pavimento}>{a.pavimento}</span></td>
                      <td><span className="trunc mut">{a.disciplina}</span></td>
                      <td><span className="trunc" title={a.servico}>{a.servico}</span></td>
                      <td className="rgt">
                        <span className="num mut">
                          {new Date(a.inicio + 'T00:00:00').toLocaleDateString('pt-BR')}
                        </span>
                      </td>
                      <td className="rgt"><span className="ncbadge">{a.dias}d</span></td>
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
            Nenhuma atividade com prazo vencido sem início.
          </div>
        )}
      </section>
    </>
  )
}
