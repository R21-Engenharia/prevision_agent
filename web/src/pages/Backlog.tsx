import { useMemo, useState } from 'react'
import { baixarRelatorio, type Backlog as BacklogData, type StatusFVS } from '../lib/api'
import { TabelaFVS } from '../components/TabelaFVS'
import { normalizar } from '../lib/texto'

const STATUS_OPCOES: Array<{ id: StatusFVS; label: string }> = [
  { id: 'NAO_INICIADA', label: 'Não iniciadas' },
  { id: 'EM_ANDAMENTO', label: 'Em andamento' },
  { id: 'FINALIZADA', label: 'Finalizadas' },
]

export function Backlog({ data }: { data: BacklogData }) {
  // Conjunto vazio = todos os status
  const [status, setStatus] = useState<Set<StatusFVS>>(new Set())
  const [modelo, setModelo] = useState('')
  const [pavimento, setPavimento] = useState('')
  const [busca, setBusca] = useState('')

  const alternarStatus = (s: StatusFVS) =>
    setStatus((atual) => {
      const novo = new Set(atual)
      if (novo.has(s)) novo.delete(s)
      else novo.add(s)
      return novo
    })

  const filtradas = useMemo(() => {
    // normalizar() espelha o filtro da API — garante que o Excel exportado
    // contenha exatamente as linhas mostradas aqui.
    const termo = normalizar(busca.trim())
    return data.rows.filter((r) => {
      if (status.size > 0 && !status.has(r.status)) return false
      if (modelo && r.modelo !== modelo) return false
      if (pavimento && r.floor !== pavimento) return false
      if (termo) {
        const alvo = normalizar(`${r.modelo} ${r.local} ${r.floor} ${r.wbs}`)
        if (!alvo.includes(termo)) return false
      }
      return true
    })
  }, [data.rows, status, modelo, pavimento, busca])

  const temFiltro = status.size > 0 || modelo || pavimento || busca
  const limpar = () => {
    setStatus(new Set()); setModelo(''); setPavimento(''); setBusca('')
  }

  const [baixando, setBaixando] = useState(false)
  const [erroExport, setErroExport] = useState<string | null>(null)

  async function exportar() {
    setErroExport(null)
    setBaixando(true)
    try {
      await baixarRelatorio(data.obra, { status: [...status], modelo, pavimento, busca })
    } catch (e) {
      setErroExport((e as Error).message)
    } finally {
      setBaixando(false)
    }
  }

  return (
    <>
      <div className="pagehead reveal">
        <div>
          <div className="eyebrow">{data.obra}</div>
          <h1>Backlog FVS</h1>
          <div className="sub">Todos os pacotes liberados e o status de cada FVS associada.</div>
        </div>
      </div>

      <div className="filters reveal" style={{ animationDelay: '.06s' }}>
        <div className="field">
          <label>Status <span className="hint">(pode marcar mais de um)</span></label>
          <div className="segmented">
            <button
              className={status.size === 0 ? 'on' : ''}
              onClick={() => setStatus(new Set())}
              aria-pressed={status.size === 0}
            >
              Todas
              <span className="ct">{data.total}</span>
            </button>
            {STATUS_OPCOES.map((o) => (
              <button
                key={o.id}
                className={status.has(o.id) ? 'on' : ''}
                onClick={() => alternarStatus(o.id)}
                aria-pressed={status.has(o.id)}
              >
                {status.has(o.id) && (
                  <svg className="chk" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="3.5" aria-hidden="true">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                )}
                {o.label}
                <span className="ct">{data.contagem[o.id]}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="f-modelo">Modelo</label>
          <select id="f-modelo" value={modelo} onChange={(e) => setModelo(e.target.value)}>
            <option value="">Todos</option>
            {data.facetas.modelos.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-pav">Pavimento</label>
          <select id="f-pav" value={pavimento} onChange={(e) => setPavimento(e.target.value)}>
            <option value="">Todos</option>
            {data.facetas.pavimentos.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>

        <div className="field grow">
          <label htmlFor="f-busca">Buscar</label>
          <input
            id="f-busca"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="modelo, local, pavimento ou WBS"
          />
        </div>

        {temFiltro && <button className="clear" onClick={limpar}>Limpar filtros</button>}
      </div>

      <div className="resultbar">
        <span className="cnt">
          <b>{filtradas.length}</b> de {data.total} FVS
        </span>

        <button
          className="btn primary"
          onClick={exportar}
          disabled={filtradas.length === 0 || baixando}
          title="Baixa um Excel com exatamente estas FVS"
        >
          <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
          </svg>
          {baixando ? 'Gerando…' : `Exportar ${filtradas.length} FVS`}
        </button>
      </div>

      {erroExport && <div className="errbox" style={{ marginBottom: 12 }}>{erroExport}</div>}

      {filtradas.length > 0 ? (
        <TabelaFVS linhas={filtradas} />
      ) : (
        <div className="panel">
          <div className="empty">
            Nenhuma FVS corresponde aos filtros. <br />
            <button className="clear" onClick={limpar}>Limpar filtros</button>
          </div>
        </div>
      )}
    </>
  )
}
