"""
Página de login do FVS Dashboard.

render_login_page(auth, app_url) → bool
    Retorna True se o usuário está autenticado, False caso contrário.
    Quando retorna False, já renderizou o formulário de login e a aplicação
    deve chamar st.stop() em seguida.
"""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from fvs_dashboard.auth.supabase_auth import SupabaseAuth


# ── CSS da página de login ─────────────────────────────────────────────────────

_LOGIN_CSS = """
<style>
/* Esconde a sidebar na tela de login */
[data-testid="stSidebar"]               { display: none !important; }
[data-testid="stSidebarCollapsedControl"]{ display: none !important; }
[data-testid="collapsedControl"]         { display: none !important; }

/* Container geral */
.login-card {
    background: #ffffff;
    border: 1px solid #e0e6f0;
    border-radius: 16px;
    padding: 2.2rem 2.4rem 2rem;
    box-shadow: 0 4px 24px rgba(26,39,68,0.10);
    margin-top: 1.5rem;
}
.login-header {
    text-align: center;
    padding-bottom: 1.4rem;
}
.login-header .brand-icon  { font-size: 40px; }
.login-header .brand-title {
    font-size: 22px;
    font-weight: 800;
    color: #1a2744;
    margin-top: 6px;
    letter-spacing: -0.3px;
}
.login-header .brand-sub {
    font-size: 12px;
    color: #6b7fa3;
    margin-top: 3px;
    letter-spacing: 0.2px;
}
/* Divisor "ou continue com" */
.or-divider {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 1rem 0 0.8rem;
}
.or-divider hr  { flex:1; border:none; border-top:1px solid #e8edf5; margin:0; }
.or-divider span{ font-size:11px; color:#9ba8bf; white-space:nowrap; }
/* Botão Google customizado */
.google-btn-wrap a {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 9px 16px;
    border: 1.5px solid #dadce0;
    border-radius: 8px;
    background: #fff;
    font-size: 13px;
    font-weight: 500;
    color: #3c4043;
    text-decoration: none;
    transition: background 0.12s, border-color 0.12s;
    width: 100%;
    box-sizing: border-box;
}
.google-btn-wrap a:hover { background:#f8f9fa; border-color:#c0c6cf; }
.google-svg { width:18px; height:18px; }
/* Rodapé */
.login-footer {
    text-align: center;
    font-size: 11px;
    color: #9ba8bf;
    margin-top: 1.4rem;
    padding-top: 1rem;
    border-top: 1px solid #f0f4fa;
}
</style>
"""

# SVG do logo Google
_GOOGLE_SVG = """<svg class="google-svg" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
</svg>"""


# ── Handler do callback OAuth (Google) ────────────────────────────────────────

def _inject_oauth_hash_handler() -> None:
    """
    Injeta JavaScript que converte o fragmento #access_token=... (retornado
    pelo Supabase após login Google) em query params que o Python pode ler.

    Funciona porque os iframes de components.html no Streamlit têm
    sandbox="allow-scripts allow-same-origin", permitindo acessar window.top.
    """
    components.html(
        """
        <script>
        (function() {
            try {
                var hash = window.top.location.hash;
                if (hash && hash.indexOf('access_token') !== -1) {
                    var params = new URLSearchParams(hash.substring(1));
                    var at = params.get('access_token') || '';
                    var rt = params.get('refresh_token') || '';
                    if (at) {
                        var clean = window.top.location.pathname
                            + '?oauth_at=' + encodeURIComponent(at)
                            + '&oauth_rt=' + encodeURIComponent(rt);
                        window.top.location.replace(clean);
                    }
                }
            } catch (e) { /* cross-origin ou hash vazio — ignorar */ }
        })();
        </script>
        """,
        height=0,
    )


def _handle_oauth_callback(auth: SupabaseAuth) -> bool:
    """
    Verifica se há tokens OAuth nos query params (após redirect do Google).
    Se sim, cria a sessão e salva em st.session_state.
    Retorna True se a sessão foi criada com sucesso.
    """
    at = st.query_params.get("oauth_at", "")
    rt = st.query_params.get("oauth_rt", "")
    if not at:
        return False

    with st.spinner("Verificando credenciais Google..."):
        try:
            user = auth.set_session_from_token(at, rt)
            email = (user.email or "").strip().lower()
            if not auth.is_authorized(email):
                auth.logout()
                st.query_params.clear()
                st.error(
                    f"⛔ O e-mail **{email}** não tem acesso autorizado. "
                    "Solicite acesso ao administrador."
                )
                return False

            role = auth.get_role(email)
            nome = (user.user_metadata or {}).get("full_name") or email
            st.session_state["auth_user"]  = user
            st.session_state["auth_email"] = email
            st.session_state["auth_nome"]  = nome
            st.session_state["auth_role"]  = role
            st.query_params.clear()
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao processar login Google: {exc}")
            st.query_params.clear()

    return False


# ── Ponto de entrada principal ─────────────────────────────────────────────────

def render_login_page(auth: SupabaseAuth, app_url: str = "") -> bool:
    """
    Renderiza a página de login/cadastro.

    Retorna True  → usuário autenticado, o app pode continuar.
    Retorna False → formulário exibido, o app deve chamar st.stop().
    """
    # 1. Injetar handler do hash OAuth
    _inject_oauth_hash_handler()

    # 2. Processar callback Google (tokens na URL)
    if _handle_oauth_callback(auth):
        return True

    # 3. Sessão já existe → autenticado
    if "auth_user" in st.session_state:
        return True

    # 4. Mostrar formulário
    _render_form(auth, app_url)
    return False


# ── Formulário de login/cadastro ───────────────────────────────────────────────

def _render_form(auth: SupabaseAuth, app_url: str) -> None:
    """Renderiza o formulário com abas Login / Criar Conta."""

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # Layout centralizado (3 colunas — centro ocupa 40% da largura)
    _, col, _ = st.columns([1.2, 2, 1.2])

    with col:
        # ── Cabeçalho ────────────────────────────────────────────────────────
        st.markdown(
            """
            <div class="login-card">
                <div class="login-header">
                    <div class="brand-icon">🏗️</div>
                    <div class="brand-title">FVS Dashboard</div>
                    <div class="brand-sub">R21 Empreendimentos — Portal de Qualidade</div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Abas ─────────────────────────────────────────────────────────────
        tab_in, tab_up = st.tabs(["Entrar", "Criar Conta"])

        # ── Aba: Entrar ───────────────────────────────────────────────────────
        with tab_in:
            email_i = st.text_input(
                "E-mail", key="li_email", placeholder="seu@email.com",
                label_visibility="collapsed",
            )
            st.caption("E-mail")
            senha_i = st.text_input(
                "Senha", key="li_senha", type="password",
                placeholder="••••••••", label_visibility="collapsed",
            )
            st.caption("Senha")

            if st.button("Entrar", use_container_width=True, type="primary", key="li_btn"):
                if not email_i or not senha_i:
                    st.warning("Preencha e-mail e senha.")
                else:
                    with st.spinner("Autenticando..."):
                        try:
                            user  = auth.login(email_i, senha_i)
                            email = (user.email or "").strip().lower()
                            if not auth.is_authorized(email):
                                auth.logout()
                                st.error("⛔ Acesso não autorizado para este e-mail.")
                            else:
                                role = auth.get_role(email)
                                nome = (user.user_metadata or {}).get("full_name") or email
                                st.session_state["auth_user"]  = user
                                st.session_state["auth_email"] = email
                                st.session_state["auth_nome"]  = nome
                                st.session_state["auth_role"]  = role
                                st.rerun()
                        except Exception as exc:
                            _msg = str(exc).lower()
                            if "invalid" in _msg or "credentials" in _msg:
                                st.error("E-mail ou senha incorretos.")
                            elif "email not confirmed" in _msg:
                                st.warning(
                                    "Confirme seu e-mail antes de entrar. "
                                    "Verifique sua caixa de entrada."
                                )
                            else:
                                st.error(f"Erro ao entrar: {exc}")

            # ── Botão Google ──────────────────────────────────────────────────
            if app_url:
                try:
                    _gurl = auth.google_auth_url(app_url)
                    # Renderiza botão como link HTML com target="_top"
                    # para navegar o frame principal (não o iframe)
                    st.markdown(
                        f"""
                        <div class="or-divider"><hr><span>ou continue com</span><hr></div>
                        <div class="google-btn-wrap">
                            <a href="{_gurl}" target="_top">
                                {_GOOGLE_SVG}
                                Entrar com Google
                            </a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                except Exception:
                    st.caption("_(Google OAuth não configurado no Supabase)_")

        # ── Aba: Criar Conta ──────────────────────────────────────────────────
        with tab_up:
            st.caption("Apenas e-mails previamente autorizados pelo administrador podem criar conta.")

            nome_c   = st.text_input("Nome completo", key="su_nome",   placeholder="Seu nome")
            email_c  = st.text_input("E-mail",        key="su_email",  placeholder="seu@email.com")
            senha_c  = st.text_input("Senha",         key="su_senha",  type="password",
                                     placeholder="Mínimo 6 caracteres")
            senha_c2 = st.text_input("Confirmar senha", key="su_senha2", type="password",
                                     placeholder="Repita a senha")

            if st.button("Criar Conta", use_container_width=True, type="primary", key="su_btn"):
                if not email_c or not senha_c:
                    st.warning("Preencha e-mail e senha.")
                elif senha_c != senha_c2:
                    st.error("As senhas não coincidem.")
                elif len(senha_c) < 6:
                    st.error("A senha deve ter pelo menos 6 caracteres.")
                else:
                    with st.spinner("Criando conta..."):
                        try:
                            auth.signup(email_c, senha_c, nome_c)
                            st.success(
                                "✅ Conta criada com sucesso! Verifique seu e-mail para "
                                "confirmar o cadastro e depois volte para entrar."
                            )
                        except PermissionError as exc:
                            st.error(f"⛔ {exc}")
                        except Exception as exc:
                            _msg = str(exc).lower()
                            if "already registered" in _msg or "already exists" in _msg:
                                st.warning(
                                    "Este e-mail já possui uma conta. Use a aba **Entrar**."
                                )
                            else:
                                st.error(f"Erro ao criar conta: {exc}")

        # ── Rodapé ────────────────────────────────────────────────────────────
        st.markdown(
            """
            <div class="login-footer">
                Problemas de acesso? Fale com o administrador do sistema.
            </div>
            </div>
            """,  # fecha .login-card
            unsafe_allow_html=True,
        )


# ── Painel de gerenciamento de emails (admin) ──────────────────────────────────

def render_admin_panel(auth: SupabaseAuth) -> None:
    """
    Painel de gerenciamento de emails autorizados.
    Chamar apenas para usuários com role='admin'.
    """
    st.markdown("### 🔐 Emails Autorizados")

    authorized = auth.list_authorized()
    if authorized:
        import pandas as pd
        df = pd.DataFrame(authorized)[["email", "nome", "role", "created_at"]]
        df.columns = ["E-mail", "Nome", "Role", "Desde"]
        df["Desde"] = pd.to_datetime(df["Desde"]).dt.strftime("%d/%m/%Y")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum email cadastrado.")

    st.divider()
    col_add, col_rem = st.columns(2)

    with col_add:
        st.markdown("**Adicionar email**")
        new_email = st.text_input("E-mail", key="adm_email", placeholder="novo@email.com")
        new_nome  = st.text_input("Nome",   key="adm_nome",  placeholder="Nome do usuário")
        new_role  = st.selectbox("Role", ["viewer", "admin"], key="adm_role")
        if st.button("Adicionar", use_container_width=True, key="adm_add"):
            if new_email:
                try:
                    auth.add_authorized(new_email, new_nome, new_role)
                    st.success(f"✅ {new_email} adicionado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro: {exc}")
            else:
                st.warning("Informe um e-mail.")

    with col_rem:
        st.markdown("**Remover email**")
        emails_list = [r["email"] for r in authorized] if authorized else []
        rem_email = st.selectbox("Selecionar", [""] + emails_list, key="adm_rem_sel")
        if st.button("Remover", use_container_width=True, key="adm_rem", type="secondary"):
            if rem_email:
                if rem_email == st.session_state.get("auth_email"):
                    st.error("Você não pode remover seu próprio acesso.")
                else:
                    try:
                        auth.remove_authorized(rem_email)
                        st.success(f"✅ {rem_email} removido.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro: {exc}")
            else:
                st.warning("Selecione um e-mail.")
