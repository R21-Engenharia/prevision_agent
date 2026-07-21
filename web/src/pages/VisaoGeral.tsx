import type { Overview } from '../lib/api'
import { CountUp } from '../components/CountUp'
import { Donut } from '../components/Donut'
import { EvolucaoChart } from '../components/EvolucaoChart'

const fmtPct = (n: number) => `${n.toFixed(1).replace('.', ',')}%`

function Kpi({
  label, value, delta, deltaTone = '', alert = false, delay,
}: {
  label: string; value: number; delta: string
  deltaTone?: 'up' | 'red' | ''; alert?: boolean; delay: number
}) {
  return (
    <div className="kpi reveal" style={{ animationDelay: `${delay}s` }}>
      <div className="lbl">
        <span className={alert ? 'tag red' : 'tag'} />
        {label}
      </div>
      <div className="val num"><CountUp value={value} /></div>
      <div className="foot">
        <span className={`delta ${deltaTone}`}>{delta}</span>
      </div>
    </div>
  )
}

export function VisaoGeral({ data }: { data: Overview }) {
  const k = data.kpis
  const o = data.obra_total

  // Estatísticas da série (reais, calculadas do payload)
  const serie = data.evolucao
  const meta = data.evolucao_meta
  const real = meta.fonte === 'snapshots'
  const ultimos = serie.slice(-12)
  const totalPeriodo = ultimos.reduce((s, p) => s + p.finalizada, 0)
  const media = ultimos.length ? totalPeriodo / ultimos.length : 0
  const ultimo = ultimos.at(-1)?.finalizada ?? 0
  const penultimo = ultimos.at(-2)?.finalizada ?? 0
  const variacao = penultimo > 0 ? ((ultimo - penultimo) / penultimo) * 100 : 0

  const ncPorFvs = k.fvs_com_nc > 0 ? k.nc_total / k.fvs_com_nc : 0
  const pctComNc = k.total_fvs > 0 ? (k.fvs_com_nc / k.total_fvs) * 100 : 0

  const agingMax = Math.max(1, ...data.aging.map((a) => a.qtd))
  const temAging = data.aging.some((a) => a.qtd > 0)
  const maxPend = Math.max(1, ...data.top_modelos.map((m) => m.pendentes))

  return (
    <>
      <div className="pagehead reveal">
        <div>
          <div className="eyebrow">{data.obra}</div>
          <h1>Visão geral</h1>
          <div className="sub">Indicadores operacionais de FVS para pacotes liberados.</div>
        </div>
        <div className="headmeta">
          <span className="st"><span className="live" />Sistema operacional</span>
          <div className="ts">
            INMETA {data.cache.inmeta.replace('ha ', '')} · PREVISION {data.cache.prevision.replace('ha ', '')}
          </div>
        </div>
      </div>

      {/* Universo completo da obra — contexto separado dos KPIs do backlog,
          para o total do InMeta não ser confundido com o backlog operacional. */}
      <section className="obrabar reveal" style={{ animationDelay: '.02s' }}>
        <div className="ob-lbl">
          <span className="ob-tag">Obra completa</span>
          <span className="ob-src">histórico InMeta</span>
        </div>
        <div className="ob-stats">
          <div className="ob-item">
            <span className="ob-v num"><CountUp value={o.realizadas} /></span>
            <span className="ob-k">inspeções realizadas</span>
          </div>
          <div className="ob-item">
            <span className="ob-v num"><CountUp value={o.concluidas} /></span>
            <span className="ob-k">concluídas</span>
          </div>
          <div className="ob-item">
            <span className="ob-v num"><CountUp value={o.em_andamento} /></span>
            <span className="ob-k">em andamento</span>
          </div>
          <div className="ob-item">
            <span className="ob-v num alerta"><CountUp value={o.nc_abertas} /></span>
            <span className="ob-k">NC abertas</span>
          </div>
        </div>
      </section>

      <div className="secao-lbl reveal" style={{ animationDelay: '.03s' }}>
        Backlog operacional
        <span className="secao-hint">
          pacotes executados 100% que ainda aguardam conferência final
        </span>
      </div>

      <section className="kpis">
        <Kpi label="Pacotes liberados" value={k.pacotes_liberados} delta="execução 100%" delay={0.04} />
        <Kpi label="Total de FVS" value={k.total_fvs} delta="associadas" delay={0.08} />
        <Kpi label="Finalizadas" value={k.finalizada} delta={fmtPct(k.pct_finalizada)} deltaTone="up" delay={0.12} />
        <Kpi label="Em andamento" value={k.em_andamento} delta={fmtPct(k.pct_em_andamento)} delay={0.16} />
        <Kpi
          label="Não iniciadas"
          value={k.nao_iniciada}
          delta={fmtPct(k.pct_nao_iniciada)}
          deltaTone={k.nao_iniciada > 0 ? 'red' : ''}
          alert={k.nao_iniciada > 0}
          delay={0.2}
        />
      </section>

      <section className="bento">
        <div className="panel reveal" style={{ animationDelay: '.14s' }}>
          <div className="phead">
            <div>
              <h2>{real ? 'Evolução do backlog' : 'Inspeções por mês de execução'}</h2>
              <div className="ph-sub">
                {real
                  ? 'histórico real · estado do backlog em cada dia'
                  : 'status atual agrupado pelo mês da inspeção'}
              </div>
            </div>
            <div className="legendpill">
              <span><i style={{ background: 'var(--accent)' }} />finalizadas</span>
            </div>
          </div>

          {!real && (
            <div className="aviso-fonte">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" />
              </svg>
              <span>
                Não é histórico congelado: mostra o <b>status de hoje</b> na data em que a
                inspeção foi feita — se uma FVS antiga for finalizada agora, o passado do
                gráfico muda. O InMeta não informa data de finalização.
                {meta.dias_faltam > 0 && (
                  <> Histórico real em <b>{meta.dias_faltam} {meta.dias_faltam === 1 ? 'dia' : 'dias'}</b> de
                  coleta ({meta.dias_snap} já registrados).</>
                )}
              </span>
            </div>
          )}

          {serie.length > 0 ? (
            <>
              <EvolucaoChart dados={serie} meta={meta} />
              {/* Com snapshots os pontos são ESTOQUE (quantas estão finalizadas
                  naquele dia) — somar não faz sentido. Com inspeções são FLUXO
                  mensal, aí soma e média valem. */}
              <div className="chart-cap">
                {real ? (
                  <>
                    <div>
                      <div className="c-k">hoje</div>
                      <div className="c-v num">{ultimo} <span className="unit">finalizadas</span></div>
                    </div>
                    <div>
                      <div className="c-k">desde o 1º registro</div>
                      <div className="c-v num">
                        +{ultimo - (serie[0]?.finalizada ?? 0)} <span className="unit">fvs</span>
                      </div>
                    </div>
                    <div>
                      <div className="c-k">dias registrados</div>
                      <div className="c-v num">{meta.dias_snap}</div>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <div className="c-k">último mês</div>
                      <div className="c-v num">
                        {ultimo}
                        {variacao !== 0 && (
                          <span className="up" style={{ color: variacao < 0 ? 'var(--accent-ink)' : undefined }}>
                            {variacao > 0 ? '↑' : '↓'}{Math.abs(variacao).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="c-k">média</div>
                      <div className="c-v num">{media.toFixed(1).replace('.', ',')} <span className="unit">/mês</span></div>
                    </div>
                    <div>
                      <div className="c-k">no período</div>
                      <div className="c-v num">{totalPeriodo} <span className="unit">insp.</span></div>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="empty">Sem histórico de inspeções para esta obra.</div>
          )}
        </div>

        <div className="panel reveal" style={{ animationDelay: '.2s' }}>
          <div className="phead">
            <div>
              <h2>Distribuição por status</h2>
              <div className="ph-sub">{k.total_fvs} fvs liberadas</div>
            </div>
          </div>
          <Donut
            total={k.total_fvs}
            segments={[
              { label: 'Finalizada', value: k.finalizada, color: 'var(--done)' },
              { label: 'Em andamento', value: k.em_andamento, color: 'var(--prog)' },
              { label: 'Não iniciada', value: k.nao_iniciada, color: 'var(--accent)' },
            ]}
          />
        </div>
      </section>

      <section className="lower">
        <div className="panel reveal" style={{ animationDelay: '.16s' }}>
          <div className="phead">
            <div>
              <h2>Não-conformidades</h2>
              <div className="ph-sub">estado atual do canteiro</div>
            </div>
          </div>
          <div className="nc-hero">
            <span className="big num"><CountUp value={k.nc_total} /></span>
            <span className="u">NC abertas no total</span>
          </div>

          {k.fvs_com_nc > 0 ? (
            <div className="nc-note">
              <svg className="ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
              </svg>
              <span><b>{k.fvs_com_nc} FVS</b> possuem não-conformidades pendentes de tratamento.</span>
            </div>
          ) : (
            <div className="empty">Nenhuma não-conformidade aberta.</div>
          )}

          <div className="nc-split">
            <div><div className="v num">{k.fvs_com_nc}</div><div className="k">fvs com nc</div></div>
            <div><div className="v num">{ncPorFvs.toFixed(1).replace('.', ',')}</div><div className="k">nc / fvs</div></div>
            <div><div className="v num">{pctComNc.toFixed(0)}%</div><div className="k">do total</div></div>
          </div>
        </div>

        <div className="panel reveal" style={{ animationDelay: '.22s' }}>
          <div className="phead">
            <div>
              <h2>Aging de pendentes</h2>
              <div className="ph-sub">tempo sem abertura no inmeta</div>
            </div>
          </div>
          {temAging ? (
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
          ) : (
            <div className="empty">Snapshots ainda não disponíveis para esta obra.</div>
          )}
        </div>
      </section>

      <section className="panel reveal" style={{ animationDelay: '.18s' }}>
        <div className="phead">
          <div>
            <h2>Modelos com mais pendências</h2>
            <div className="ph-sub">em andamento + não iniciadas · por modelo</div>
          </div>
        </div>
        {data.top_modelos.length > 0 ? (
          <div className="rank">
            {data.top_modelos.map((m, i) => {
              const codigo = m.modelo.match(/^FVS[\s\d.]+/)?.[0]?.trim() ?? ''
              const nome = m.modelo.replace(/^FVS[\s\d.]+-\s*/, '')
              const critico = m.nao_iniciada > 0
              return (
                <div className="rrow" key={m.modelo}>
                  <span className="rk num">{String(i + 1).padStart(2, '0')}</span>
                  <span className="rn">
                    {nome} {codigo && <small className="code">{codigo}</small>}
                  </span>
                  <span className="bar">
                    <i style={{
                      width: `${(m.pendentes / maxPend) * 100}%`,
                      background: critico ? 'var(--accent)' : 'var(--prog)',
                    }} />
                  </span>
                  <span className="rv">
                    <span className={critico ? 'red num' : 'num'}>{m.pendentes}</span>
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="empty">Nenhuma pendência registrada.</div>
        )}
      </section>

      <div className="foot-note">
        <span className="chip">dados reais</span>
        Prevision + InMeta · atualizado automaticamente a cada carga.
      </div>
    </>
  )
}
