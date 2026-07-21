import { useMemo, useState } from 'react'
import { STATUS_LABEL, type LinhaFVS, type StatusFVS } from '../lib/api'

const CLASSE: Record<StatusFVS, string> = {
  FINALIZADA: 'fin',
  EM_ANDAMENTO: 'and',
  NAO_INICIADA: 'nao',
}

export function StatusPill({ status }: { status: StatusFVS }) {
  return (
    <span className={`pill ${CLASSE[status]}`}>
      <i />
      {STATUS_LABEL[status]}
    </span>
  )
}

type Coluna = 'floor' | 'wbs' | 'modelo' | 'local' | 'status' | 'pct_exec' | 'nc' | 'data_ins'

// `larg` alimenta o <colgroup>: com table-layout fixed a tabela cabe inteira
// na tela, sem rolagem horizontal. Textos longos truncam com reticências.
const COLUNAS: Array<{ id: Coluna; label: string; rgt?: boolean; larg: string }> = [
  { id: 'floor', label: 'Pavimento', larg: '15%' },
  { id: 'wbs', label: 'WBS', larg: '8%' },
  { id: 'modelo', label: 'Modelo FVS', larg: '26%' },
  { id: 'local', label: 'Local', larg: '20%' },
  { id: 'status', label: 'Status', larg: '13%' },
  { id: 'pct_exec', label: '% Exec', rgt: true, larg: '7%' },
  { id: 'nc', label: 'NC', rgt: true, larg: '5%' },
  { id: 'data_ins', label: 'Inspeção', rgt: true, larg: '10%' },
]

const ORDEM_STATUS: Record<StatusFVS, number> = {
  NAO_INICIADA: 0,
  EM_ANDAMENTO: 1,
  FINALIZADA: 2,
}

/** Tabela de FVS com ordenação por coluna. `colunas` limita quais aparecem. */
export function TabelaFVS({
  linhas,
  colunas = COLUNAS.map((c) => c.id),
}: {
  linhas: LinhaFVS[]
  colunas?: Coluna[]
}) {
  const [ordem, setOrdem] = useState<{ col: Coluna; asc: boolean }>({ col: 'status', asc: true })
  const visiveis = COLUNAS.filter((c) => colunas.includes(c.id))

  const ordenadas = useMemo(() => {
    const copia = [...linhas]
    copia.sort((a, b) => {
      let r: number
      if (ordem.col === 'status') {
        r = ORDEM_STATUS[a.status] - ORDEM_STATUS[b.status]
      } else if (ordem.col === 'nc' || ordem.col === 'pct_exec') {
        r = (a[ordem.col] ?? -1) - (b[ordem.col] ?? -1)
      } else {
        r = String(a[ordem.col] ?? '').localeCompare(String(b[ordem.col] ?? ''), 'pt-BR')
      }
      return ordem.asc ? r : -r
    })
    return copia
  }, [linhas, ordem])

  const alternar = (col: Coluna) =>
    setOrdem((o) => (o.col === col ? { col, asc: !o.asc } : { col, asc: true }))

  return (
    <div className="tablewrap">
      <table className="data">
        <colgroup>
          {visiveis.map((c) => (
            <col key={c.id} style={{ width: c.larg }} />
          ))}
          <col style={{ width: 40 }} />
        </colgroup>
        <thead>
          <tr>
            {visiveis.map((c) => (
              <th
                key={c.id}
                onClick={() => alternar(c.id)}
                className={c.rgt ? 'rgt' : undefined}
                style={c.rgt ? { textAlign: 'right' } : undefined}
                aria-sort={ordem.col === c.id ? (ordem.asc ? 'ascending' : 'descending') : 'none'}
              >
                {c.label}
                {ordem.col === c.id && <span className="arw">{ordem.asc ? '↑' : '↓'}</span>}
              </th>
            ))}
            <th aria-label="Link" />
          </tr>
        </thead>
        <tbody>
          {/*
            A chave inclui o índice: a mesma atividade pode ter duas FVS do
            mesmo modelo (locais distintos), e act_id+modelo colide — o que
            faria o React duplicar/omitir linhas.
          */}
          {ordenadas.map((r, i) => (
            <tr key={`${r.act_id}-${r.wbs}-${i}`}>
              {visiveis.map((c) => {
                switch (c.id) {
                  case 'floor':
                    return <td key={c.id}><span className="trunc" title={r.floor}>{r.floor}</span></td>
                  case 'wbs':
                    return <td key={c.id}><span className="num mut">{r.wbs}</span></td>
                  case 'modelo':
                    return <td key={c.id}><span className="trunc" title={r.modelo}>{r.modelo}</span></td>
                  case 'local':
                    return <td key={c.id}><span className="trunc mut" title={r.local}>{r.local}</span></td>
                  case 'status':
                    return <td key={c.id}><StatusPill status={r.status} /></td>
                  case 'pct_exec':
                    return (
                      <td key={c.id} className="rgt">
                        <span className="num mut">{r.pct_exec === null ? '—' : `${r.pct_exec}%`}</span>
                      </td>
                    )
                  case 'nc':
                    return (
                      <td key={c.id} className="rgt">
                        {r.nc > 0 ? <span className="ncbadge">{r.nc}</span> : <span className="num mut">—</span>}
                      </td>
                    )
                  case 'data_ins':
                    return <td key={c.id} className="rgt"><span className="num mut">{r.data_ins || '—'}</span></td>
                  default:
                    return null
                }
              })}
              <td className="rgt">
                {r.link ? (
                  <a className="linkico" href={r.link} target="_blank" rel="noopener noreferrer"
                     aria-label={`Abrir ${r.modelo} no InMeta`}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 4h6v6M20 4l-8 8M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5" />
                    </svg>
                  </a>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
