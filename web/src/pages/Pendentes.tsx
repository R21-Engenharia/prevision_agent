import { useMemo, useState } from 'react'
import type { Backlog as BacklogData, LinhaFVS } from '../lib/api'
import { TabelaFVS } from '../components/TabelaFVS'
import { normalizar } from '../lib/texto'

export function Pendentes({ data }: { data: BacklogData }) {
  const [busca, setBusca] = useState('')

  const pendentes = useMemo(
    () => data.rows.filter((r) => r.status === 'NAO_INICIADA'),
    [data.rows],
  )

  const grupos = useMemo(() => {
    const termo = normalizar(busca.trim())
    const alvo = termo
      ? pendentes.filter((r) => normalizar(`${r.modelo} ${r.local} ${r.floor}`).includes(termo))
      : pendentes

    const mapa = new Map<string, LinhaFVS[]>()
    for (const r of alvo) {
      const lista = mapa.get(r.modelo) ?? []
      lista.push(r)
      mapa.set(r.modelo, lista)
    }
    return [...mapa.entries()].sort((a, b) => b[1].length - a[1].length)
  }, [pendentes, busca])

  const totalFiltrado = grupos.reduce((s, [, l]) => s + l.length, 0)

  if (pendentes.length === 0) {
    return (
      <>
        <div className="pagehead reveal">
          <div>
            <div className="eyebrow">{data.obra}</div>
            <h1>Pendentes</h1>
            <div className="sub">FVS ainda não abertas no InMeta.</div>
          </div>
        </div>
        <div className="okbanner">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 6L9 17l-5-5" />
          </svg>
          Todas as FVS de pacotes liberados já foram abertas no InMeta.
        </div>
      </>
    )
  }

  return (
    <>
      <div className="pagehead reveal">
        <div>
          <div className="eyebrow">{data.obra}</div>
          <h1>Pendentes</h1>
          <div className="sub">FVS ainda não abertas no InMeta — ação imediata necessária.</div>
        </div>
      </div>

      <div className="banner reveal" style={{ animationDelay: '.06s' }}>
        <svg className="ic" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
        </svg>
        <div>
          <div className="bt">
            {pendentes.length} {pendentes.length === 1 ? 'FVS não foi aberta' : 'FVS não foram abertas'} no InMeta
          </div>
          <div className="bs">
            Pacotes com execução 100% em campo aguardando abertura da verificação de serviço.
          </div>
        </div>
      </div>

      <div className="filters">
        <div className="field grow">
          <label htmlFor="p-busca">Buscar</label>
          <input
            id="p-busca"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="modelo, local ou pavimento"
          />
        </div>
      </div>

      <div className="resultbar">
        <span className="cnt">
          <b>{totalFiltrado}</b> pendentes · {grupos.length} {grupos.length === 1 ? 'modelo' : 'modelos'}
        </span>
      </div>

      {grupos.map(([modelo, linhas], i) => (
        <details className="group" key={modelo} open={i < 3}>
          <summary>
            <svg className="chev" width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M9 6l6 6-6 6" />
            </svg>
            <span className="gname">{modelo}</span>
            <span className="gct">{linhas.length}</span>
          </summary>
          <div className="gbody">
            <TabelaFVS linhas={linhas} colunas={['floor', 'wbs', 'local', 'pct_exec']} />
          </div>
        </details>
      ))}

      {grupos.length === 0 && (
        <div className="panel"><div className="empty">Nenhuma pendência corresponde à busca.</div></div>
      )}
    </>
  )
}
