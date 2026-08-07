import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

interface Msg { role: 'user' | 'assistant'; content: string }

const SUGESTOES = [
  'Quais serviços estão travando mais a obra?',
  'O que falta finalizar no último pavimento?',
  'Qual disciplina está mais atrasada?',
  'Quais pendências são só de FVS?',
]

/** Assistente da Obra — chat em linguagem natural sobre os dados da obra. */
export function AssistenteObra({ obra }: { obra: string }) {
  const [aberto, setAberto] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [texto, setTexto] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const fim = useRef<HTMLDivElement>(null)

  // troca de obra zera a conversa
  useEffect(() => { setMsgs([]); setErro(null) }, [obra])
  useEffect(() => { fim.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, carregando])

  async function enviar(pergunta: string) {
    const q = pergunta.trim()
    if (!q || carregando) return
    setErro(null)
    setTexto('')
    const anteriores = msgs.slice(-6)   // histórico SEM a pergunta atual
    setMsgs([...msgs, { role: 'user' as const, content: q }])
    setCarregando(true)
    try {
      const r = await api.chatAgente(obra, q, anteriores)
      setMsgs((m) => [...m, { role: 'assistant', content: r.resposta }])
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setCarregando(false)
    }
  }

  return (
    <div className={aberto ? 'assist aberto' : 'assist'}>
      <button className="assist-head" onClick={() => setAberto((a) => !a)}>
        <span className="assist-ic">✦</span>
        <div className="assist-head-txt">
          <b>Assistente da Obra</b>
          <span>pergunte em português sobre {obra}</span>
        </div>
        <span className={aberto ? 'assist-cv open' : 'assist-cv'}>▾</span>
      </button>

      {aberto && (
        <div className="assist-corpo">
          <div className="assist-msgs">
            {msgs.length === 0 && !carregando && (
              <div className="assist-vazio">
                <p>Faça uma pergunta ou comece por uma sugestão:</p>
                <div className="assist-sug">
                  {SUGESTOES.map((s) => (
                    <button key={s} onClick={() => void enviar(s)}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`assist-msg ${m.role}`}>{m.content}</div>
            ))}
            {carregando && <div className="assist-msg assistant carregando">pensando…</div>}
            {erro && <div className="assist-erro">{erro}</div>}
            <div ref={fim} />
          </div>

          <div className="assist-input">
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void enviar(texto) }}
              placeholder="Pergunte sobre a obra…"
              disabled={carregando}
            />
            <button onClick={() => void enviar(texto)} disabled={carregando || !texto.trim()}>
              Enviar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
