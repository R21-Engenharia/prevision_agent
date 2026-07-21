import { useMemo } from 'react'
import type { LinhaGantt } from '../lib/api'

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

const COR_STATUS: Record<string, string> = {
  'Finalizada':   '#1E8E5A',
  'Em andamento': '#D98A00',
  'Nao iniciada': '#8A94A6',
  'Atrasada':     'var(--accent)',
}

const dia = (iso: string) => new Date(iso + 'T00:00:00').getTime()
const UM_DIA = 86_400_000

/** Marcas de mês dentro do intervalo, para o eixo do topo. */
function marcasDeMes(ini: number, fim: number) {
  const marcas: Array<{ pos: number; label: string; ano: boolean }> = []
  const d = new Date(ini)
  d.setDate(1)
  if (d.getTime() < ini) d.setMonth(d.getMonth() + 1)
  const total = fim - ini
  while (d.getTime() <= fim) {
    marcas.push({
      pos: ((d.getTime() - ini) / total) * 100,
      label: MESES[d.getMonth()],
      ano: d.getMonth() === 0,
    })
    d.setMonth(d.getMonth() + 1)
  }
  return marcas
}

export function Gantt({
  linhas, de, ate, hoje,
}: {
  linhas: LinhaGantt[]
  de: string
  ate: string
  hoje: string
}) {
  const ini = dia(de)
  const fim = dia(ate) + UM_DIA
  const total = Math.max(fim - ini, UM_DIA)

  const marcas = useMemo(() => marcasDeMes(ini, fim), [ini, fim])
  const posHoje = ((dia(hoje) - ini) / total) * 100
  const hojeVisivel = posHoje >= 0 && posHoje <= 100

  const fmt = (iso: string) =>
    new Date(iso + 'T00:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })

  return (
    <div className="gantt">
      <div className="gantt-eixo">
        <div className="gantt-rot" />
        <div className="gantt-trilha">
          {marcas.map((m, i) => (
            <span key={i} className={m.ano ? 'gm ano' : 'gm'} style={{ left: `${m.pos}%` }}>
              {m.label}
            </span>
          ))}
        </div>
      </div>

      <div className="gantt-corpo">
        {hojeVisivel && (
          <div className="gantt-hoje" style={{ left: `calc(var(--rot-w) + (100% - var(--rot-w)) * ${posHoje / 100})` }}>
            <span>hoje</span>
          </div>
        )}

        {linhas.map((l, i) => {
          const x = ((dia(l.inicio) - ini) / total) * 100
          const w = Math.max(((dia(l.fim) + UM_DIA - dia(l.inicio)) / total) * 100, 0.6)
          const cor = COR_STATUS[l.status] ?? 'var(--prog)'
          return (
            <div className="gantt-linha" key={`${l.pavimento}-${i}`}>
              <div className="gantt-rot" title={l.pavimento}>{l.pavimento}</div>
              <div className="gantt-trilha">
                {marcas.map((m, j) => (
                  <i key={j} className="gantt-grade" style={{ left: `${m.pos}%` }} />
                ))}
                <div
                  className="gantt-barra"
                  style={{ left: `${x}%`, width: `${w}%`, background: cor }}
                  title={`${l.pavimento}\n${fmt(l.inicio)} – ${fmt(l.fim)}\n${l.atividades} atividades · ${l.pct.toFixed(0)}% avanço\n${l.status}`}
                >
                  {l.pct > 0 && l.pct < 100 && (
                    <span className="gantt-prog" style={{ width: `${l.pct}%` }} />
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="gantt-legenda">
        {Object.entries(COR_STATUS).map(([nome, cor]) => (
          <span key={nome}><i style={{ background: cor }} />{nome}</span>
        ))}
      </div>
    </div>
  )
}
