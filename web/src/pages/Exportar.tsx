import { useState } from 'react'
import { baixarRelatorioFVS, type Formato, type Overview } from '../lib/api'
import { CountUp } from '../components/CountUp'

const ICONE_DOWNLOAD = (
  <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
  </svg>
)

export function Exportar({ data, obra }: { data: Overview | null; obra: string }) {
  const [incluirFin, setIncluirFin] = useState(true)
  const [baixando, setBaixando] = useState<Formato | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  const k = data?.kpis
  const noRelatorio = k
    ? (incluirFin ? k.total_fvs : k.total_fvs - k.finalizada)
    : 0

  async function exportar(formato: Formato) {
    setErro(null)
    setBaixando(formato)
    try {
      await baixarRelatorioFVS(obra, formato, incluirFin)
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setBaixando(null)
    }
  }

  return (
    <>
      <div className="pagehead reveal">
        <div>
          <div className="eyebrow">{obra}</div>
          <h1>Exportar</h1>
          <div className="sub">Relatórios de FVS com os dados atuais.</div>
        </div>
      </div>

      {erro && <div className="errbox" style={{ marginBottom: 13 }}>{erro}</div>}

      <section className="panel reveal" style={{ animationDelay: '.06s' }}>
        <div className="phead">
          <div>
            <h2>Conteúdo</h2>
            <div className="ph-sub">o que entra nos arquivos</div>
          </div>
        </div>

        <label className="opcao">
          <input type="checkbox" checked={incluirFin}
                 onChange={(e) => setIncluirFin(e.target.checked)} />
          <span>
            <b>Incluir FVS finalizadas</b>
            <small>
              Desmarque para exportar apenas o que está pendente
              (em andamento e não iniciadas).
            </small>
          </span>
        </label>

        {k && (
          <div className="nc-split" style={{ marginTop: 18 }}>
            <div>
              <div className="v num"><CountUp value={noRelatorio} /></div>
              <div className="k">fvs no relatório</div>
            </div>
            <div>
              <div className="v num"><CountUp value={k.pacotes_liberados} /></div>
              <div className="k">pacotes liberados</div>
            </div>
            <div>
              <div className="v num" style={{ color: k.nao_iniciada > 0 ? 'var(--accent-ink)' : undefined }}>
                <CountUp value={k.nao_iniciada} />
              </div>
              <div className="k">não iniciadas</div>
            </div>
          </div>
        )}
      </section>

      <section className="lower">
        <div className="panel reveal" style={{ animationDelay: '.1s' }}>
          <div className="phead">
            <div>
              <h2>Excel completo</h2>
              <div className="ph-sub">4 abas · resumo, backlog, pendentes, por modelo</div>
            </div>
          </div>
          <p className="exp-desc">
            Planilha com todas as FVS e um resumo por modelo. Use quando precisar
            filtrar, cruzar ou repassar os dados.
          </p>
          <button className="btn primary" style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => exportar('excel')} disabled={baixando !== null || !obra}>
            {ICONE_DOWNLOAD}
            {baixando === 'excel' ? 'Gerando…' : 'Baixar Excel'}
          </button>
        </div>

        <div className="panel reveal" style={{ animationDelay: '.14s' }}>
          <div className="phead">
            <div>
              <h2>PDF resumo</h2>
              <div className="ph-sub">2 páginas · kpis + fvs não iniciadas</div>
            </div>
          </div>
          <p className="exp-desc">
            Resumo operacional pronto para imprimir ou anexar em ata. Foca no que
            precisa de ação.
          </p>
          <button className="btn" style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => exportar('pdf')} disabled={baixando !== null || !obra}>
            {ICONE_DOWNLOAD}
            {baixando === 'pdf' ? 'Gerando…' : 'Baixar PDF'}
          </button>
        </div>
      </section>

      {data && (
        <div className="foot-note">
          <span className="chip">dados atuais</span>
          Prevision {data.cache.prevision} · InMeta {data.cache.inmeta}
        </div>
      )}
    </>
  )
}
