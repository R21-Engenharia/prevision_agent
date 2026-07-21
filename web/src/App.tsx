import { useCallback, useEffect, useState } from 'react'
import {
  api, setTokenProvider,
  type Auditoria as AuditoriaData, type Backlog as BacklogData,
  type Decoracao as DecoracaoData,
  type Overview, type Periodo, type Tempo as TempoData,
} from './lib/api'
import { authConfigurada, resolverUsuario, supabase, type Usuario } from './lib/supabase'
import { Shell } from './components/Shell'
import { Login } from './pages/Login'
import { VisaoGeral } from './pages/VisaoGeral'
import { Backlog } from './pages/Backlog'
import { Pendentes } from './pages/Pendentes'
import { Auditoria } from './pages/Auditoria'
import { Tempo } from './pages/Tempo'
import { Decoracao } from './pages/Decoracao'
import { Exportar } from './pages/Exportar'

type Theme = 'light' | 'dark'

function initialTheme(): Theme {
  const saved = localStorage.getItem('fvs-theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const PRECISA_BACKLOG = new Set(['backlog', 'pendentes'])

/** Usuário fictício quando a autenticação não está configurada (dev local). */
const USUARIO_DEV: Usuario = { email: 'dev@local', nome: 'Desenvolvimento', papel: 'admin' }

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [usuario, setUsuario] = useState<Usuario | null>(authConfigurada ? null : USUARIO_DEV)
  const [checandoSessao, setChecandoSessao] = useState(authConfigurada)
  const [erroAcesso, setErroAcesso] = useState<string | null>(null)

  const [obras, setObras] = useState<string[]>([])
  const [obra, setObra] = useState<string>('')
  const [page, setPage] = useState('visao-geral')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [backlog, setBacklog] = useState<BacklogData | null>(null)
  const [auditoria, setAuditoria] = useState<AuditoriaData | null>(null)
  const [tempo, setTempo] = useState<TempoData | null>(null)
  const [decoracao, setDecoracao] = useState<DecoracaoData | null>(null)
  // Decoração tem filtros próprios (obra pode ser 'todas')
  const [decObra, setDecObra] = useState('')
  const [decDisc, setDecDisc] = useState('')
  const [decStatus, setDecStatus] = useState('')
  // Auditoria tem filtros próprios: obra pode ser "todas", período é dela.
  const [audObra, setAudObra] = useState('')
  const [audPeriodo, setAudPeriodo] = useState<Periodo>('Tudo')
  const [erro, setErro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(true)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('fvs-theme', theme)
  }, [theme])

  // ── Sessão Supabase ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!supabase) return

    // O token vai no header Authorization de toda chamada à API.
    setTokenProvider(async () => {
      const { data } = await supabase.auth.getSession()
      return data.session?.access_token ?? null
    })

    async function aplicarSessao(sessao: import('@supabase/supabase-js').Session | null) {
      if (!sessao?.user?.email) {
        setUsuario(null)
        setChecandoSessao(false)
        return
      }
      const meta = sessao.user.user_metadata as { full_name?: string } | undefined
      const u = await resolverUsuario(sessao.user.email, meta?.full_name ?? '')
      if (!u) {
        // Autenticou no Supabase, mas não está autorizado neste app.
        setErroAcesso(`O e-mail ${sessao.user.email} não tem acesso autorizado.`)
        await supabase!.auth.signOut()
        setUsuario(null)
      } else {
        setErroAcesso(null)
        setUsuario(u)
      }
      setChecandoSessao(false)
    }

    supabase.auth.getSession().then(({ data }) => void aplicarSessao(data.session))
    const { data: sub } = supabase.auth.onAuthStateChange((_evt, sessao) => {
      void aplicarSessao(sessao)
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  // ── Dados ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!usuario) return
    api.obras()
      .then((r) => {
        setObras(r.obras)
        setObra((atual) => atual || r.obras[0] || '')
      })
      .catch((e: Error) => {
        setErro(e.message)
        setCarregando(false)
      })
  }, [usuario])

  const carregar = useCallback(async (alvo: string, pagina: string) => {
    setCarregando(true)
    setErro(null)
    try {
      if (pagina === 'decoracao') {
        setDecoracao(await api.decoracao(decObra, decDisc, decStatus))
      } else if (pagina === 'tempo') {
        setTempo(await api.tempo())
      } else if (pagina === 'auditoria') {
        setAuditoria(await api.auditoria(audObra, audPeriodo))
      } else if (!alvo) {
        return
      } else if (pagina === 'exportar') {
        setOverview(await api.overview(alvo))
      } else if (PRECISA_BACKLOG.has(pagina)) {
        setBacklog(await api.backlog(alvo))
      } else {
        setOverview(await api.overview(alvo))
      }
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setCarregando(false)
    }
  }, [audObra, audPeriodo, decObra, decDisc, decStatus])

  useEffect(() => {
    if (usuario) void carregar(obra, page)
  }, [obra, page, carregar, usuario])

  useEffect(() => { setBacklog(null); setOverview(null) }, [obra])

  async function sair() {
    if (supabase) await supabase.auth.signOut()
    setUsuario(null)
  }

  // ── Gate de autenticação ───────────────────────────────────────────────────
  if (checandoSessao) {
    return (
      <div className="login-wrap">
        <div className="skel" style={{ width: 392, height: 300, borderRadius: 18 }} />
      </div>
    )
  }

  if (!usuario) {
    return (
      <>
        {erroAcesso && (
          <div className="login-wrap" style={{ minHeight: 'auto', paddingBottom: 0 }}>
            <div className="login-erro" style={{ maxWidth: 392, width: '100%' }}>{erroAcesso}</div>
          </div>
        )}
        <Login />
      </>
    )
  }

  const esqueleto = (
    <div style={{ display: 'grid', gap: 13 }}>
      <div className="skel" style={{ height: 92 }} />
      <div className="skel" style={{ height: 300 }} />
      <div className="skel" style={{ height: 220 }} />
    </div>
  )

  function conteudo() {
    if (erro) {
      return (
        <div className="errbox">
          <b>Não foi possível carregar os dados</b>
          {erro} — verifique se a API está no ar em <span className="code">localhost:8001</span>.
        </div>
      )
    }
    if (page === 'visao-geral') return overview ? <VisaoGeral data={overview} /> : esqueleto
    if (page === 'backlog') return backlog ? <Backlog data={backlog} /> : esqueleto
    if (page === 'pendentes') return backlog ? <Pendentes data={backlog} /> : esqueleto
    if (page === 'exportar') return <Exportar data={overview} obra={obra} />
    if (page === 'tempo') return tempo ? <Tempo data={tempo} /> : esqueleto
    if (page === 'decoracao') {
      return decoracao ? (
        <Decoracao data={decoracao} obra={decObra} disciplina={decDisc} status={decStatus}
                   obras={obras} onObra={setDecObra} onDisciplina={setDecDisc}
                   onStatus={setDecStatus} />
      ) : esqueleto
    }
    if (page === 'auditoria') {
      return auditoria ? (
        <Auditoria
          data={auditoria}
          obra={audObra}
          periodo={audPeriodo}
          obras={obras}
          onObra={setAudObra}
          onPeriodo={setAudPeriodo}
        />
      ) : esqueleto
    }
    return (
      <div className="panel">
        <div className="phead">
          <div>
            <h2>Em construção</h2>
            <div className="ph-sub">próxima fase da migração</div>
          </div>
        </div>
        <div className="empty">Esta tela ainda roda no Streamlit. Será migrada nas próximas fases.</div>
      </div>
    )
  }

  return (
    <Shell
      page={page}
      onNavigate={setPage}
      obras={obras}
      obra={obra}
      onObraChange={setObra}
      onRefresh={() => void carregar(obra, page)}
      refreshing={carregando}
      syncLabel={overview?.cache.inmeta.replace('ha ', '') ?? '—'}
      theme={theme}
      onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      usuario={usuario}
      onSair={sair}
      authAtiva={authConfigurada}
    >
      {conteudo()}
    </Shell>
  )
}
