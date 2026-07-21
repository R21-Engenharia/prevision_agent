import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { EvolucaoMeta, EvolucaoPonto } from '../lib/api'

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

/** Snapshots são pontos diários; inspeções são agregados mensais. */
function rotulo(iso: string, porDia: boolean) {
  const d = new Date(iso + 'T00:00:00')
  return porDia
    ? `${String(d.getDate()).padStart(2, '0')}/${MESES[d.getMonth()]}`
    : `${MESES[d.getMonth()]}/${String(d.getFullYear()).slice(2)}`
}

interface TipProps {
  active?: boolean
  payload?: Array<{ payload: EvolucaoPonto & { label: string } }>
  porDia?: boolean
}

function Tip({ active, payload, porDia }: TipProps) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tooltip">
      <div className="t-k">{p.label}</div>
      <div className="t-v num">{p.finalizada} finalizadas</div>
      <div className="t-k" style={{ marginTop: 5, marginBottom: 0 }}>
        {porDia
          ? `${p.em_andamento ?? 0} em andamento · ${p.nao_iniciada ?? 0} não iniciadas`
          : `${p.total} inspeções · ${p.nc_total ?? 0} NC`}
      </div>
    </div>
  )
}

export function EvolucaoChart({
  dados, meta,
}: {
  dados: EvolucaoPonto[]
  meta: EvolucaoMeta
}) {
  const porDia = meta.fonte === 'snapshots'
  const data = dados.map((d) => ({ ...d, label: rotulo(d.data, porDia) }))

  return (
    <div style={{ marginTop: 14, width: '100%', height: 200 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
          <defs>
            <linearGradient id="grad-fin" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.22} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--hairline)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--faint)', fontSize: 10, fontFamily: 'var(--mono)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--hairline)' }}
            interval="preserveStartEnd"
            minTickGap={22}
          />
          <YAxis
            tick={{ fill: 'var(--faint)', fontSize: 10, fontFamily: 'var(--mono)' }}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <Tooltip
            content={<Tip porDia={porDia} />}
            cursor={{ stroke: 'var(--hairline-2)', strokeDasharray: '3 3' }}
          />
          <Area
            type="monotone"
            dataKey="finalizada"
            stroke="var(--accent)"
            strokeWidth={2.4}
            fill="url(#grad-fin)"
            dot={porDia ? { r: 3, fill: 'var(--surface)', stroke: 'var(--accent)', strokeWidth: 2 } : false}
            activeDot={{ r: 4.5, fill: 'var(--surface)', stroke: 'var(--accent)', strokeWidth: 2.5 }}
            animationDuration={1100}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
