import { createClient, type SupabaseClient } from '@supabase/supabase-js'

/**
 * Cliente Supabase — mesma base que o app Streamlit já usa.
 *
 * As credenciais vêm de web/.env.local (não versionado):
 *   VITE_SUPABASE_URL=https://xxxx.supabase.co
 *   VITE_SUPABASE_ANON_KEY=eyJ...
 *
 * A chave anon é pública por design (o acesso real é controlado por RLS no
 * Supabase). Sem as duas variáveis o app roda em modo aberto de
 * desenvolvimento — igual ao comportamento atual do Streamlit local.
 */
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const authConfigurada = Boolean(url && anonKey)

export const supabase: SupabaseClient | null = authConfigurada
  ? createClient(url!, anonKey!, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  : null

/** Domínios liberados automaticamente, separados por vírgula. */
const dominiosLiberados = String(import.meta.env.VITE_ALLOWED_DOMAINS ?? '')
  .split(',')
  .map((d) => d.trim().toLowerCase())
  .filter(Boolean)

export interface Usuario {
  email: string
  nome: string
  papel: 'admin' | 'viewer'
}

/**
 * Verifica se o e-mail tem acesso e qual o papel.
 * Espelha a regra de auth/supabase_auth.py: domínio liberado entra como
 * viewer; senão precisa estar na tabela authorized_emails.
 */
export async function resolverUsuario(
  email: string,
  nomeFallback: string,
): Promise<Usuario | null> {
  const alvo = email.trim().toLowerCase()

  let papel: 'admin' | 'viewer' | null = null
  if (supabase) {
    try {
      const { data } = await supabase
        .from('authorized_emails')
        .select('role, nome')
        .eq('email', alvo)
        .maybeSingle()
      if (data) {
        papel = data.role === 'admin' ? 'admin' : 'viewer'
        if (data.nome) nomeFallback = data.nome
      }
    } catch {
      // tabela indisponível — cai para a checagem por domínio
    }
  }

  if (!papel) {
    const dominio = alvo.split('@')[1] ?? ''
    if (dominiosLiberados.includes(dominio)) papel = 'viewer'
  }

  if (!papel) return null
  return { email: alvo, nome: nomeFallback || alvo, papel }
}
