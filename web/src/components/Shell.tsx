import type { ReactNode } from 'react'
import type { Usuario } from '../lib/supabase'

const PAGES = [
  { id: 'visao-geral', label: 'Visão geral', group: 'Operação', icon: 'grid' },
  { id: 'backlog', label: 'Backlog FVS', group: 'Operação', icon: 'list' },
  { id: 'pendentes', label: 'Pendentes', group: 'Operação', icon: 'clock' },
  { id: 'exportar', label: 'Exportar', group: 'Operação', icon: 'down' },
  { id: 'auditoria', label: 'Auditoria', group: 'Operação', icon: 'bars' },
  { id: 'tempo', label: 'Condição do tempo', group: 'Cronograma', icon: 'trend' },
  { id: 'decoracao', label: 'Decoração', group: 'Cronograma', icon: 'home' },
] as const

const PATHS: Record<string, string> = {
  grid: 'M3 13h8V3H3zM13 21h8v-8h-8zM13 3v6h8V3zM3 21h8v-4H3z',
  list: 'M4 6h16M4 12h16M4 18h10',
  clock: 'M12 8v4l3 2',
  down: 'M12 3v12m0 0l-4-4m4 4l4-4M4 21h16',
  bars: 'M4 19V5m4 14v-8m4 8V9m4 10V7m4 12V11',
  trend: 'M3 15l4-4 3 3 7-7M21 7v4h-4',
  home: 'M4 21V8l8-5 8 5v13M9 21v-6h6v6',
}

function Icon({ name }: { name: string }) {
  return (
    <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      {name === 'clock' && <circle cx="12" cy="12" r="9" />}
      <path d={PATHS[name]} />
    </svg>
  )
}

interface ShellProps {
  page: string
  onNavigate: (id: string) => void
  obras: string[]
  obra: string
  onObraChange: (o: string) => void
  onRefresh: () => void
  refreshing: boolean
  syncLabel: string
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  usuario: Usuario
  onSair: () => void
  authAtiva: boolean
  children: ReactNode
}

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean)
  if (partes.length === 0) return '?'
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase()
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase()
}

export function Shell({
  page, onNavigate, obras, obra, onObraChange, onRefresh,
  refreshing, syncLabel, theme, onToggleTheme, usuario, onSair, authAtiva, children,
}: ShellProps) {
  const groups = ['Operação', 'Cronograma']
  const current = PAGES.find((p) => p.id === page)

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <div className="mark">R</div>
          <div className="wm">
            FVS Dashboard
            <small>r21.eng / qualidade</small>
          </div>
        </div>

        <div className="cmd">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4-4" />
          </svg>
          Buscar
          <span className="kbd">⌘K</span>
        </div>

        {groups.map((g) => (
          <div key={g}>
            <div className="navlbl">{g}</div>
            <nav className="nav">
              {PAGES.filter((p) => p.group === g).map((p) => (
                <button
                  key={p.id}
                  className={p.id === page ? 'active' : ''}
                  onClick={() => onNavigate(p.id)}
                  aria-current={p.id === page ? 'page' : undefined}
                >
                  <Icon name={p.icon} />
                  {p.label}
                </button>
              ))}
            </nav>
          </div>
        ))}

        <div className="spacer" />
        <div className="who">
          <div className="av">{iniciais(usuario.nome)}</div>
          <div className="who-txt">
            <div className="nm" title={usuario.email}>{usuario.nome}</div>
            <div className="rl">{authAtiva ? usuario.papel : 'modo dev · sem login'}</div>
          </div>
          {authAtiva && (
            <button className="sairbtn" onClick={onSair} aria-label="Sair da conta" title="Sair">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
            </button>
          )}
        </div>
      </aside>

      <main>
        <header className="top">
          <div className="crumb">
            <span>Qualidade</span>
            <span className="sep">/</span>
            <b>{current?.label ?? 'Visão geral'}</b>
          </div>

          <div className="toolset">
            <span className="sync">
              <span className="pulse" />
              sync · {syncLabel}
            </span>

            <div className="selectwrap">
              <span className="dot" />
              <select
                className="obra"
                value={obra}
                onChange={(e) => onObraChange(e.target.value)}
                aria-label="Selecionar obra"
              >
                {obras.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
              <span className="cv">▾</span>
            </div>

            <button
              className="icobtn"
              onClick={onToggleTheme}
              aria-label={theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro'}
            >
              {theme === 'dark' ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
                </svg>
              )}
            </button>

            {/* A exportação vive na tela de Backlog, onde há filtros para
                aplicar ao relatório — evita um botão global sem contexto. */}
            <button
              className={refreshing ? 'icobtn spin' : 'icobtn'}
              onClick={onRefresh}
              aria-label="Atualizar dados"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 12a8 8 0 018-8 8 8 0 017 4M20 12a8 8 0 01-8 8 8 8 0 01-7-4" />
                <path d="M17 4v4h4M7 20v-4H3" />
              </svg>
            </button>
          </div>
        </header>

        <div className="content">{children}</div>
      </main>
    </div>
  )
}
