import { useState, type FormEvent } from 'react'
import { supabase } from '../lib/supabase'

const GOOGLE_SVG = (
  <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" />
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
  </svg>
)

/** Traduz erros do Supabase para algo acionável pelo usuário. */
function mensagemAmigavel(bruto: string): string {
  const m = bruto.toLowerCase()
  if (m.includes('failed to fetch') || m.includes('network') || m.includes('load failed')) {
    return 'Não foi possível conectar ao servidor de autenticação. ' +
           'Verifique sua conexão — se persistir, avise o administrador.'
  }
  if (m.includes('invalid') || m.includes('credentials')) return 'E-mail ou senha incorretos.'
  if (m.includes('not confirmed')) return 'Confirme seu e-mail antes de entrar.'
  if (m.includes('rate limit') || m.includes('too many')) {
    return 'Muitas tentativas seguidas. Aguarde um minuto e tente de novo.'
  }
  return bruto
}

export function Login() {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function entrar(e: FormEvent) {
    e.preventDefault()
    if (!supabase) return
    setErro(null)
    setEnviando(true)
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: email.trim().toLowerCase(),
        password: senha,
      })
      if (error) setErro(mensagemAmigavel(error.message))
      // Sucesso: o listener de sessão no App assume daqui.
    } catch (e) {
      // Falha de rede lança em vez de retornar error
      setErro(mensagemAmigavel((e as Error).message))
    } finally {
      setEnviando(false)
    }
  }

  async function entrarComGoogle() {
    if (!supabase) return
    setErro(null)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: window.location.origin },
      })
      if (error) setErro(mensagemAmigavel(error.message))
    } catch (e) {
      setErro(mensagemAmigavel((e as Error).message))
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-head">
          <div className="mark">R</div>
          <div className="lc-tag">R21 Empreendimentos</div>
          <div className="lc-title">FVS Dashboard</div>
          <div className="lc-sub">Portal de Qualidade</div>
        </div>

        <form onSubmit={entrar} className="login-form">
          <div className="field">
            <label htmlFor="lg-email">E-mail</label>
            <input
              id="lg-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nome@r21empreendimentos.com"
              required
            />
          </div>

          <div className="field">
            <label htmlFor="lg-senha">Senha</label>
            <input
              id="lg-senha"
              type="password"
              autoComplete="current-password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          {erro && <div className="login-erro">{erro}</div>}

          <button className="btn primary lg-btn" type="submit" disabled={enviando}>
            {enviando ? 'Entrando…' : 'Entrar'}
          </button>
        </form>

        <div className="ou-divisor"><hr /><span>ou continue com</span><hr /></div>

        <button className="btn google" onClick={entrarComGoogle} type="button">
          {GOOGLE_SVG} Entrar com Google
        </button>

        <div className="login-rodape">
          Problemas de acesso? Fale com o administrador do sistema.
        </div>
      </div>
    </div>
  )
}
