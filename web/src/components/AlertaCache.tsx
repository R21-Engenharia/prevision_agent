import { LIMITE_HORAS, type Overview } from '../lib/api'

const FONTES = [
  { chave: 'prevision' as const, nome: 'Prevision',
    explica: 'as atividades e o cálculo de pacotes liberados' },
  { chave: 'inmeta' as const, nome: 'InMeta',
    explica: 'o status das inspeções e as não-conformidades' },
]

function porExtenso(horas: number): string {
  if (horas < 48) return `${Math.round(horas)} horas`
  return `${Math.floor(horas / 24)} dias`
}

/**
 * Avisa quando uma fonte de dados parou de atualizar.
 *
 * Existe por causa de um caso real: a coleta do Prevision quebrou e ficou 69
 * dias sem rodar. O app informava a idade do cache, mas num canto da barra
 * lateral — ninguém percebeu, e a operação decidiu com dado velho esse tempo
 * todo. Aqui o aviso fica no caminho, onde não dá para ignorar.
 */
export function AlertaCache({ data }: { data: Overview }) {
  const velhas = FONTES
    .map((f) => ({ ...f, horas: data.cache_horas?.[f.chave] ?? null }))
    .filter((f) => f.horas !== null && f.horas > LIMITE_HORAS[f.chave])

  if (velhas.length === 0) return null

  return (
    <div className="alerta-cache reveal">
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
      </svg>
      <div>
        <div className="ac-titulo">
          {velhas.length === 1
            ? `Dados do ${velhas[0].nome} desatualizados`
            : 'Dados desatualizados'}
        </div>
        <div className="ac-texto">
          {velhas.map((f) => (
            <div key={f.chave}>
              <b>{f.nome}</b> sem atualizar há <b>{porExtenso(f.horas!)}</b> —
              afeta {f.explica}.
            </div>
          ))}
          <div className="ac-acao">
            A coleta automática pode ter falhado. Verifique em{' '}
            <b>GitHub → Actions</b> se o último job ficou vermelho.
          </div>
        </div>
      </div>
    </div>
  )
}
