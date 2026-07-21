import { CountUp } from './CountUp'

export interface Segment {
  label: string
  value: number
  color: string
}

const R = 52
const C = 2 * Math.PI * R

/** Donut de status — monocromático + vermelho no que exige atenção. */
export function Donut({ segments, total }: { segments: Segment[]; total: number }) {
  let offset = 0

  return (
    <div className="donutwrap">
      <div className="donut">
        <svg viewBox="0 0 120 120" width="176" height="176" aria-hidden="true">
          <circle className="seg" cx="60" cy="60" r={R} stroke="var(--track)" />
          {segments.map((s) => {
            const len = total > 0 ? (s.value / total) * C : 0
            const dash = `${Math.max(len - 2, 0)} ${C - Math.max(len - 2, 0)}`
            const el = (
              <circle
                key={s.label}
                className="seg"
                cx="60"
                cy="60"
                r={R}
                stroke={s.color}
                strokeDasharray={dash}
                strokeDashoffset={-offset}
              />
            )
            offset += len
            return el
          })}
        </svg>
        <div className="ctr">
          <b className="num"><CountUp value={total} /></b>
          <span>fvs</span>
        </div>
      </div>

      <div className="legend">
        {segments.map((s) => {
          const pct = total > 0 ? (s.value / total) * 100 : 0
          return (
            <div className="lrow" key={s.label}>
              <div className="lr-top">
                <span className="sw" style={{ background: s.color }} />
                <span className="lname">{s.label}</span>
                <span className="lval num">{s.value}</span>
                <span className="lpct num">{pct.toFixed(1).replace('.', ',')}%</span>
              </div>
              <div className="bar">
                <i style={{ width: `${pct}%`, background: s.color }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
