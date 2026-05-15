"""
Página de login do FVS Dashboard.

render_login_page(auth, app_url) → bool
    Retorna True se o usuário está autenticado, False caso contrário.
    Quando retorna False, já renderizou o formulário de login e a aplicação
    deve chamar st.stop() em seguida.
"""
from __future__ import annotations

from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

from fvs_dashboard.auth.supabase_auth import SupabaseAuth

# ── Componente OAuth (iframe same-origin: pode ler window.top.location.hash) ──
# declare_component com path= serve os arquivos pelo mesmo domínio do app,
# o que garante acesso a window.top — diferente de st.components.v1.html
# que usa srcdoc (origem nula) e não pode acessar o frame pai.
_OAUTH_COMPONENT_DIR = Path(__file__).parent / "oauth_handler"
_oauth_component = components.declare_component(
    "fvs_oauth_handler",
    path=str(_OAUTH_COMPONENT_DIR),
)


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



# ── Handler do callback OAuth (Google) ────────────────────────────────────────

def _inject_oauth_hash_handler() -> None:
    """
    Roda o componente OAuth (same-origin) que converte o fragmento
    #access_token=... em query params que o Python pode ler.
    Ao contrário de st.components.v1.html (srcdoc / origem nula),
    este componente é servido pelo mesmo domínio do app e pode
    acessar window.top.location sem erro de cross-origin.
    """
    _oauth_component(google_url="", key="fvs_oauth_hash", default=None)


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

            # ── Botão Google (componente same-origin) ────────────────────────
            if app_url:
                try:
                    _gurl = auth.google_auth_url(app_url)
                    st.markdown(
                        '<div class="or-divider"><hr><span>ou continue com</span><hr></div>',
                        unsafe_allow_html=True,
                    )
                    # O componente usa window.top.location.href para navegar
                    # sem depender de target= ou comportamento do navegador
                    _oauth_component(
                        google_url=_gurl,
                        key="fvs_oauth_google_btn",
                        default=None,
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
