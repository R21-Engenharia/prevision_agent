import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useMemo, useState } from 'react'
import {
  baixarRelatorioTempo,
  type Condicao, type IntervaloTempo, type Tempo as TempoData,
} from '../lib/api'
import { CountUp } from '../components/CountUp'
import { Donut } from '../components/Donut'

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
const rotuloMes = (iso: string) => {
  const [a, m] = iso.split('-')
  return `${MESES[Number(m) - 1]}/${a.slice(2)}`
}

// Categorias climáticas: exceção deliberada ao neutro do app — aqui a cor
// carrega significado (sol/nuvem/chuva) e precisa ser distinguível.
const META: Record<Condicao, { label: string; cor: string }> = {
  ENSOLARADO: { label: 'Ensolarado', cor: '#D9962B' },
  NUBLADO: { label: 'Nublado', cor: '#8497AD' },
  CHUVOSO: { label: 'Chuvoso', cor: '#3E6DA8' },
}
const ORDEM: Condicao[] = ['ENSOLARADO', 'NUBLADO', 'CHUVOSO']

const eixo = { fill: 'var(--faint)', fontSize: 10, fontFamily: 'var(--mono)' }

/** Últimos N dias a partir de uma data ISO. */
function recuar(iso: string, dias: number): string {
  const d = new Date(iso + 'T00:00:00')
  d.setDate(d.getDate() - dias)
  return d.toISOString().slice(0, 10)
}

export function Tempo({ data }: { data: TempoData }) {
  const [baixando, setBaixando] = useState(false)
  const [erroExport, setErroExport] = useState<string | null>(null)

  // Defaults: Período 1 = últimos 30 dias com registro; Período 2 = os 30 antes.
  const { min, max } = useMemo(() => {
    const datas = data.dias.map((d) => d.data).sort()
    return { min: datas[0] ?? '', max: datas.at(-1) ?? '' }
  }, [data.dias])

  const [p1, setP1] = useState<IntervaloTempo>(() => ({
    de: max ? recuar(max, 29) : '', ate: max,
  }))
  const [p2, setP2] = useState<IntervaloTempo>(() => ({
    de: max ? recuar(max, 59) : '', ate: max ? recuar(max, 30) : '',
  }))

  /** Conta as condições dentro de um intervalo (inclusive). */
  const contar = (iv: IntervaloTempo) => {
    const base: Record<Condicao, number> = { ENSOLARADO: 0, NUBLADO: 0, CHUVOSO: 0 }
    if (!iv.de || !iv.ate) return base
    for (const d of data.dias) {
      if (d.data >= iv.de && d.data <= iv.ate && d.condicao in base) {
        base[d.condicao as Condicao] += 1
      }
    }
    return base
  }

  const c1 = useMemo(() => contar(p1), [p1, data.dias])
  const c2 = useMemo(() => contar(p2), [p2, data.dias])

  async function exportar() {
    setErroExport(null)
    setBaixando(true)
    try {
      await baixarRelatorioTempo(p1, p2)
    } catch (e) {
      setErroExport((e as Error).message)
    } finally {
      setBaixando(false)
    }
  }

  if (!data.disponivel) {
    return (
      <>
        <div className="pagehead reveal">
          <div>
            <div className="eyebrow">Diário de obra · InMeta</div>
            <h1>Condição do tempo</h1>
          </div>
        </div>
        <div className="panel"><div className="empty">
          Sem dados de diário de obra. Rode uma atualização do InMeta.
        </div></div>
      </>
    )
  }

  const totalGeral = ORDEM.reduce((s, c) => s + data.totais[c], 0)
  const totalInmeta = ORDEM.reduce((s, c) => s + data.inmeta[c], 0)
  const totalHist = ORDEM.reduce((s, c) => s + data.historico[c], 0)

  const meses = data.meses.map((m) => ({ ...m, label: rotuloMes(m.mes) }))

  return (
    <>
      <div className="pagehead reveal">
        <div>
          <div className="eyebrow">Diário de obra · InMeta</div>
          <h1>Condição do tempo</h1>
          <div className="sub">
            Visão consolidada do canteiro — cada dia entra uma única vez.
          </div>
        </div>
        <div className="headmeta">
          <button className="btn primary" onClick={exportar} disabled={baixando}
                  title="Excel no padrão usado nas reuniões">
            <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
            </svg>
            {baixando ? 'Gerando…' : 'Exportar Excel'}
          </button>
          <div className="ts">
            {totalGeral} DIAS{data.coletado_em ? ` · ATUALIZADO EM ${data.coletado_em}` : ''}
          </div>
        </div>
      </div>

      {erroExport && <div className="errbox" style={{ marginBottom: 12 }}>{erroExport}</div>}

      <section className="obrabar reveal" style={{ animationDelay: '.02s' }}>
        <div className="ob-lbl">
          <span className="ob-tag">Composição</span>
          <span className="ob-src">sem duplicar dias</span>
        </div>
        <div className="ob-stats">
          <div className="ob-item">
            <span className="ob-v num"><CountUp value={totalHist} /></span>
            <span className="ob-k">histórico pré-InMeta</span>
          </div>
          <div className="ob-item">
            <span className="ob-v num"><CountUp value={totalInmeta} /></span>
            <span className="ob-k">registrados no InMeta</span>
          </div>
          {data.cobertura.map((c) => (
            <div className="ob-item" key={c.obra}>
              <span className="ob-v num"><CountUp value={c.dias_aproveitados} /></span>
              <span className="ob-k">
                de {c.obra.replace(' Residence', '')}
                {c.dias_aproveitados < c.dias_registrados && (
                  <span className="mut"> · {c.dias_registrados} no diário</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="tres-pizzas">
        <div className="panel reveal" style={{ animationDelay: '.08s' }}>
          <div className="phead">
            <div>
              <h2>Total acumulado</h2>
              <div className="ph-sub">histórico interno + inmeta</div>
            </div>
          </div>
          <Donut
            total={totalGeral}
            segments={ORDEM.map((c) => ({
              label: META[c].label,
              value: data.totais[c],
              color: META[c].cor,
            }))}
          />
        </div>

        {([[p1, setP1, c1, 'Período 1'], [p2, setP2, c2, 'Período 2']] as const).map(
          ([iv, setIv, cont, titulo], i) => {
            const tot = ORDEM.reduce((s, c) => s + cont[c], 0)
            return (
              <div className="panel reveal" key={titulo}
                   style={{ animationDelay: `${0.12 + i * 0.05}s` }}>
                <div className="phead">
                  <div>
                    <h2>{titulo}</h2>
                    <div className="ph-sub">{tot} dias no intervalo</div>
                  </div>
                </div>

                <div className="periodo-campos">
                  <div className="field">
                    <label htmlFor={`de-${i}`}>De</label>
                    <input id={`de-${i}`} type="date" value={iv.de}
                           min={min} max={max}
                           onChange={(e) => setIv({ ...iv, de: e.target.value })} />
                  </div>
                  <div className="field">
                    <label htmlFor={`ate-${i}`}>Até</label>
                    <input id={`ate-${i}`} type="date" value={iv.ate}
                           min={min} max={max}
                           onChange={(e) => setIv({ ...iv, ate: e.target.value })} />
                  </div>
                </div>

                {iv.de && iv.ate && iv.de > iv.ate ? (
                  <div className="empty">A data inicial está depois da final.</div>
                ) : tot > 0 ? (
                  <Donut
                    total={tot}
                    segments={ORDEM.map((c) => ({
                      label: META[c].label, value: cont[c], color: META[c].cor,
                    }))}
                  />
                ) : (
                  <div className="empty">Nenhum registro neste intervalo.</div>
                )}
              </div>
            )
          },
        )}
      </section>

      <section>
        <div className="panel reveal" style={{ animationDelay: '.16s' }}>
          <div className="phead">
            <div>
              <h2>Origem dos dias</h2>
              <div className="ph-sub">prioridade: {data.prioridade[0].replace(' Residence', '')}</div>
            </div>
          </div>

          <div className="aging" style={{ marginTop: 18 }}>
            {ORDEM.map((c) => {
              const hist = data.historico[c]
              const inm = data.inmeta[c]
              const tot = hist + inm
              const pct = totalGeral > 0 ? (tot / totalGeral) * 100 : 0
              return (
                <div key={c}>
                  <div className="lr-top" style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 6 }}>
                    <span className="sw" style={{ background: META[c].cor, width: 9, height: 9, borderRadius: 3 }} />
                    <span className="lname" style={{ flex: 1, fontSize: 13 }}>{META[c].label}</span>
                    <span className="lval num" style={{ fontSize: 13, fontWeight: 640 }}>{tot}</span>
                    <span className="lpct num" style={{ width: 46, textAlign: 'right', color: 'var(--faint)', fontSize: 12 }}>
                      {pct.toFixed(1).replace('.', ',')}%
                    </span>
                  </div>
                  <div className="bar">
                    <i style={{ width: `${pct}%`, background: META[c].cor }} />
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--faint)', fontFamily: 'var(--mono)', marginTop: 4 }}>
                    {hist} histórico · {inm} inmeta
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="panel reveal" style={{ animationDelay: '.14s' }}>
        <div className="phead">
          <div>
            <h2>Evolução mensal</h2>
            <div className="ph-sub">dias por condição · somente registros do inmeta</div>
          </div>
        </div>
        {meses.length > 0 ? (
          <div style={{ width: '100%', height: 260, marginTop: 14 }}>
            <ResponsiveContainer>
              <BarChart data={meses} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="var(--hairline)" vertical={false} />
                <XAxis dataKey="label" tick={eixo} tickLine={false}
                       axisLine={{ stroke: 'var(--hairline)' }} minTickGap={16} />
                <YAxis tick={eixo} tickLine={false} axisLine={false} width={40} />
                <Tooltip
                  cursor={{ fill: 'var(--surface-2)' }}
                  contentStyle={{
                    background: 'var(--surface)', border: '1px solid var(--hairline-2)',
                    borderRadius: 10, fontSize: 12.5,
                  }}
                  labelStyle={{ color: 'var(--faint)', fontFamily: 'var(--mono)', fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11.5, fontFamily: 'var(--mono)' }} />
                {ORDEM.map((c) => (
                  <Bar key={c} dataKey={c} stackId="t" name={META[c].label} fill={META[c].cor} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <div className="empty">Sem registros mensais.</div>}
      </section>

      <div className="foot-note">
        <span className="chip">consolidado</span>
        Quando as duas obras registram no mesmo dia, vale o diário de{' '}
        {data.prioridade[0].replace(' Residence', '')} — o dia nunca é contado duas vezes.
      </div>
    </>
  )
}
