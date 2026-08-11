import { useEffect, useMemo, useState } from 'react'
import { api, type DeparaItem, type EapServico } from '../lib/api'

const fmt = (n: number) => n.toLocaleString('pt-BR', { maximumFractionDigits: 0 })
const fmt2 = (n: number) => n.toLocaleString('pt-BR', { maximumFractionDigits: 2 })

const CONF: Record<DeparaItem['confianca'], { rotulo: string; cls: string }> = {
  alta:          { rotulo: 'direta', cls: 'dp-alta' },
  escolher:      { rotulo: 'escolher', cls: 'dp-escolher' },
  baixa:         { rotulo: 'revisar', cls: 'dp-baixa' },
  sem_candidato: { rotulo: 'sem match', cls: 'dp-sem' },
}

const nomeLimpo = (n: string) => n.replace(/^FVS\s+[\d.]+\s*-\s*/, '').trim()
const rup = (v: number | null, un: string | null) =>
  v == null ? '—' : `${fmt2(v)} Hh/${un ?? '?'}`

export function DeparaEAP({ obra, admin }: { obra: string; admin: boolean }) {
  const [itens, setItens] = useState<DeparaItem[] | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [soPendentes, setSoPendentes] = useState(false)
  const [salvando, setSalvando] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  useEffect(() => {
    setItens(null); setErro(null); setAviso(null)
    api.rupDepara(obra).then((r) => setItens(r.itens)).catch((e: Error) => setErro(e.message))
  }, [obra])

  const confirmados = useMemo(
    () => (itens ?? []).filter((i) => i.status === 'confirmado').length,
    [itens],
  )

  async function confirmar(fvs: string, g: EapServico) {
    setSalvando(fvs); setAviso(null)
    try {
      await api.rupConfirmarDepara(obra, fvs, g)
      setItens((atual) => (atual ?? []).map((i) => i.fvs_codigo === fvs
        ? { ...i, status: 'confirmado', confirmado: {
            eap_descricao: g.descricao, unidade: g.unidade,
            qtd_executada: g.qtd_executada, rup_real: g.rup_previa } }
        : i))
    } catch (e) {
      setAviso((e as Error).message)
    } finally {
      setSalvando(null)
    }
  }

  if (erro) return <div className="errbox"><b>Não foi possível carregar o de-para</b>{erro}</div>
  if (!itens) return <div className="skel" style={{ height: 400 }} />

  const lista = soPendentes ? itens.filter((i) => i.status !== 'confirmado') : itens

  return (
    <div className="panel">
      <div className="phead">
        <div>
          <h2>Amarração FVS → EAP (Sienge)</h2>
          <div className="ph-sub">
            Cada serviço do RDO ligado ao item de orçamento do Sienge — a ponte que traz a
            quantidade executada (denominador da RUP). O número ao lado de cada candidato é a
            RUP que resultaria: use-o pra escolher o serviço certo. {confirmados} de {itens.length} confirmados.
          </div>
        </div>
        <label className="dp-toggle">
          <input type="checkbox" checked={soPendentes}
                 onChange={(e) => setSoPendentes(e.target.checked)} />
          só pendentes
        </label>
      </div>

      {aviso && <div className="dp-aviso">{aviso}</div>}

      <div className="dp-lista">
        {lista.map((it) => {
          const conf = CONF[it.confianca]
          return (
            <div className="dp-row" key={it.fvs_codigo}>
              <div className="dp-fvs">
                <div className="dp-fvs-top">
                  <span className="num mut">{it.fvs_codigo}</span>
                  <span className={`dp-badge ${conf.cls}`}>{conf.rotulo}</span>
                </div>
                <div className="dp-fvs-nome" title={nomeLimpo(it.fvs_nome)}>{nomeLimpo(it.fvs_nome)}</div>
                <div className="dp-fvs-hh num">{fmt(it.hh_total)} Hh</div>
              </div>

              <div className="dp-cands">
                {it.status === 'confirmado' && it.confirmado ? (
                  <div className="dp-confirmado">
                    <div className="dp-cand-desc"><span className="dp-check">✓</span> {it.confirmado.eap_descricao}</div>
                    <div className="dp-cand-meta">
                      <span className="dp-rup num">{rup(it.confirmado.rup_real, it.confirmado.unidade)}</span>
                      {it.confirmado.qtd_executada != null && (
                        <span className="dp-qexec mono mut">{fmt(it.confirmado.qtd_executada)} {it.confirmado.unidade} exec.</span>
                      )}
                      {admin && (
                        <button className="dp-alterar"
                                onClick={() => setItens((a) => (a ?? []).map((i) =>
                                  i.fvs_codigo === it.fvs_codigo ? { ...i, status: 'pendente', confirmado: null } : i))}>
                          alterar
                        </button>
                      )}
                    </div>
                  </div>
                ) : it.sugestoes.length === 0 ? (
                  <div className="mut" style={{ fontSize: 13 }}>Nenhum candidato na EAP — amarração manual necessária.</div>
                ) : (
                  it.sugestoes.map((c, idx) => (
                    <button key={idx} className="dp-cand" disabled={!admin || salvando === it.fvs_codigo}
                            onClick={() => confirmar(it.fvs_codigo, c)}
                            title={admin ? 'Confirmar esta amarração' : 'Só admin confirma'}>
                      <div className="dp-cand-desc">{c.descricao}</div>
                      <div className="dp-cand-meta">
                        <span className={`dp-rup num ${c.rup_previa == null ? 'dp-rup-nulo' : ''}`}>
                          {rup(c.rup_previa, c.unidade)}
                        </span>
                        <span className="dp-qexec mono mut">
                          {c.qtd_executada > 0 ? `${fmt(c.qtd_executada)} ${c.unidade} exec.` : 'sem qtd exec.'}
                        </span>
                        {c.mao_de_obra && <span className="dp-moe">MOE</span>}
                        {c.n_linhas > 1 && <span className="dp-disc">{c.n_linhas} linhas</span>}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
