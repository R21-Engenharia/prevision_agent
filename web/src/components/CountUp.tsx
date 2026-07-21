import { useEffect, useRef, useState } from 'react'

const prefersReduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/**
 * Anima um número de 0 até `value`.
 *
 * Correção: o valor final é SEMPRE garantido. requestAnimationFrame não roda
 * em abas em segundo plano — sem a rede de segurança abaixo o número ficaria
 * congelado em 0 até o usuário focar a aba (exibindo dado errado).
 */
export function CountUp({ value, duration = 900 }: { value: number; duration?: number }) {
  const estatico = prefersReduced() || (typeof document !== 'undefined' && document.hidden)
  const [shown, setShown] = useState(estatico ? value : 0)
  const frame = useRef<number>(0)

  useEffect(() => {
    if (prefersReduced() || document.hidden) {
      setShown(value)
      return
    }

    let start: number | null = null
    const tick = (ts: number) => {
      if (start === null) start = ts
      const p = Math.min((ts - start) / duration, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      setShown(Math.round(value * eased))
      if (p < 1) frame.current = requestAnimationFrame(tick)
    }
    frame.current = requestAnimationFrame(tick)

    // Rede de segurança: se o rAF for suspenso (aba oculta), crava o valor final.
    const guard = window.setTimeout(() => setShown(value), duration + 300)

    return () => {
      cancelAnimationFrame(frame.current)
      window.clearTimeout(guard)
    }
  }, [value, duration])

  return <>{shown.toLocaleString('pt-BR')}</>
}
