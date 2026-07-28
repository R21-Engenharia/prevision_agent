import { useEffect, useRef, useState } from 'react'
import { api, type FonteRefresh } from '../lib/api'

/**
 * Menu de atualização no topo. Três ações com naturezas diferentes:
 *  - Recarregar tela: só rebusca o que a API já tem (instantâneo).
 *  - Atualizar Prevision / InMeta: dispara a coleta no GitHub. É assíncrono —
 *    o dado novo só aparece depois da coleta + redeploy, daí o ETA explícito.
 */

interface Props {
  onRecarregar: () => void
  recarregando: boolean
}

type EstadoFonte =
  | { fase: 'ocioso' }
  | { fase: 'enviando' }
  | { fase: 'ok'; mensagem: string }
  | { fase: 'erro'; mensagem: string }

const FONTES: Array<{ id: FonteRefresh; nome: string; nota: string }> = [
  { id: 'prevision', nome: 'Atualizar Prevision', nota: 'Pacotes e status · ~30 min' },
  { id: 'inmeta', nome: 'Atualizar InMeta', nota: 'Inspeções e tempo · ~8 min' },
]

export function AtualizarMenu({ onRecarregar, recarregando }: Props) {
  const [aberto, setAberto] = useState(false)
  const [estado, setEstado] = useState<Record<FonteRefresh, EstadoFonte>>({
    prevision: { fase: 'ocioso' },
    inmeta: { fase: 'ocioso' },
  })
  const wrap = useRef<HTMLDivElement>(null)

  // Fecha ao clicar fora ou apertar Esc.
  useEffect(() => {
    if (!aberto) return
    function fora(e: MouseEvent) {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setAberto(false)
    }
    function esc(e: KeyboardEvent) {
      if (e.key === 'Escape') setAberto(false)
    }
    document.addEventListener('mousedown', fora)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', fora)
      document.removeEventListener('keydown', esc)
    }
  }, [aberto])

  async function disparar(fonte: FonteRefresh) {
    setEstado((s) => ({ ...s, [fonte]: { fase: 'enviando' } }))
    try {
      const r = await api.refresh(fonte)
      setEstado((s) => ({ ...s, [fonte]: { fase: 'ok', mensagem: r.mensagem } }))
    } catch (e) {
      setEstado((s) => ({
        ...s,
        [fonte]: { fase: 'erro', mensagem: (e as Error).message },
      }))
    }
  }

  return (
    <div className="atu" ref={wrap}>
      <button
        className={recarregando ? 'icobtn spin' : 'icobtn'}
        onClick={() => setAberto((a) => !a)}
        aria-label="Atualizar dados"
        aria-expanded={aberto}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 12a8 8 0 018-8 8 8 0 017 4M20 12a8 8 0 01-8 8 8 8 0 01-7-4" />
          <path d="M17 4v4h4M7 20v-4H3" />
        </svg>
      </button>

      {aberto && (
        <div className="atu-pop" role="menu">
          <button
            className="atu-item"
            role="menuitem"
            onClick={() => {
              onRecarregar()
              setAberto(false)
            }}
          >
            <div className="atu-nm">Recarregar tela</div>
            <div className="atu-nt">Rebusca os dados já coletados · imediato</div>
          </button>

          <div className="atu-sep" />
          <div className="atu-lbl">Coletar da fonte</div>

          {FONTES.map(({ id, nome, nota }) => {
            const e = estado[id]
            return (
              <div key={id} className="atu-fonte">
                <button
                  className="atu-item"
                  role="menuitem"
                  disabled={e.fase === 'enviando'}
                  onClick={() => void disparar(id)}
                >
                  <div className="atu-nm">
                    {nome}
                    {e.fase === 'enviando' && <span className="atu-spin" aria-hidden="true" />}
                  </div>
                  <div className="atu-nt">{nota}</div>
                </button>
                {e.fase === 'ok' && <div className="atu-msg ok">{e.mensagem}</div>}
                {e.fase === 'erro' && <div className="atu-msg erro">{e.mensagem}</div>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
