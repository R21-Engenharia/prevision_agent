"""
Página de login do FVS Dashboard.

render_login_page(auth, app_url) → bool
    Retorna True se o usuário está autenticado, False caso contrário.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import streamlit as st
import streamlit.components.v1 as components

from fvs_dashboard.auth.supabase_auth import SupabaseAuth

# ── Componente OAuth (same-origin, só lê hash) ────────────────────────────────
# declare_component(path=) serve os arquivos pelo mesmo domínio do app.
# Com allow-same-origin, o JS PODE ler window.top.location.hash.
# NÃO tenta navegar window.top (bloqueado sem allow-top-navigation).
# O botão Google é feito via st.markdown <a> (fora de qualquer iframe).
_OAUTH_COMPONENT_DIR = Path(__file__).parent / "oauth_handler"
_oauth_component = components.declare_component(
    "fvs_oauth_handler",
    path=str(_OAUTH_COMPONENT_DIR),
)

# ── SVG Google ────────────────────────────────────────────────────────────────
_GOOGLE_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" '
    'style="flex-shrink:0;vertical-align:middle;">'
    '<path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 '
    '2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>'
    '<path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 '
    '1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>'
    '<path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 '
    '8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>'
    '<path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 '
    '7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>'
    "</svg>"
)

# ── CSS da página de login ─────────────────────────────────────────────────────
_LOGIN_CSS = """
<style>
[data-testid="stSidebar"]                { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="collapsedControl"]          { display: none !important; }

.login-card {
    background: #ffffff;
    border: 1px solid #e0e6f0;
    border-radius: 16px;
    padding: 2.2rem 2.4rem 2rem;
    box-shadow: 0 4px 24px rgba(26,39,68,0.10);
    margin-top: 1.5rem;
}
.login-header { text-align: center; padding-bottom: 1.4rem; }
.login-header .brand-icon  { font-size: 40px; }
.login-header .brand-title { font-size: 22px; font-weight: 800; color: #1a2744; margin-top: 6px; letter-spacing: -0.3px; }
.login-header .brand-sub   { font-size: 12px; color: #6b7fa3; margin-top: 3px; }

.or-divider { display:flex; align-items:center; gap:10px; margin:1rem 0 0.8rem; }
.or-divider hr   { flex:1; border:none; border-top:1px solid #e8edf5; margin:0; }
.or-divider span { font-size:11px; color:#9ba8bf; white-space:nowrap; }

/* Botão Google — <a> direto no Streamlit, sem iframe */
.g-oauth-btn {
    display: flex !important;
    align-items: center;
    justify-content: center;
    gap: 10px;
    width: 100%;
    padding: 9px 16px;
    border: 1.5px solid #dadce0 !important;
    border-radius: 8px;
    background: #fff !important;
    font-size: 13px;
    font-weight: 500;
    color: #3c4043 !important;
    text-decoration: none !important;
    box-sizing: border-box;
    transition: background 0.12s, border-color 0.12s;
    cursor: pointer;
}
.g-oauth-btn:hover { background: #f8f9fa !important; border-color: #c0c6cf !important; }

.login-footer {
    text-align: center; font-size: 11px; color: #9ba8bf;
    margin-top: 1.4rem; padding-top: 1rem; border-top: 1px solid #f0f4fa;
}
</style>
"""


# ── Processar tokens do hash OAuth ────────────────────────────────────────────

def _parse_hash(hash_str: str) -> tuple[str, str]:
    """Extrai access_token e refresh_token de uma string de hash OAuth."""
    tokens: dict[str, str] = {}
    for item in hash_str.lstrip("#").split("&"):
        if "=" in item:
            k, v = item.split("=", 1)
            tokens[k.strip()] = unquote(v.strip())
    return tokens.get("access_token", ""), tokens.get("refresh_token", "")


def _process_oauth_hash(auth: SupabaseAuth, hash_str: str) -> bool:
    """
    Tenta criar sessão Supabase a partir dos tokens no hash OAuth.
    Retorna True se autenticado com sucesso.
    """
    at, rt = _parse_hash(hash_str)
    if not at:
        return False

    with st.spinner("Verificando credenciais Google..."):
        try:
            user  = auth.set_session_from_token(at, rt)
            email = (user.email or "").strip().lower()
            if not auth.is_authorized(email):
                auth.logout()
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
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao processar login Google: {exc}")

    return False


# ── Ponto de entrada ───────────────────────────────────────────────────────────

def render_login_page(auth: SupabaseAuth, app_url: str = "") -> bool:
    """
    Renderiza a tela de login.
    Retorna True se autenticado, False caso contrário.
    """
    # 1. Sessão já ativa?
    if "auth_user" in st.session_state:
        return True

    # 2. Componente same-origin lê window.top.location.hash e devolve ao Python.
    #    Na 1ª renderização devolve "" (default).
    #    Na 2ª (após o JS do componente rodar) devolve o hash real.
    _hash = _oauth_component(key="fvs_oauth_hash", default="")

    # 3. Processar tokens vindos do Google OAuth
    if _hash and "access_token" in _hash:
        if _process_oauth_hash(auth, _hash):
            return True

    # 4. Verificar query params legados (fallback de sessões anteriores)
    _at = st.query_params.get("oauth_at", "")
    _rt = st.query_params.get("oauth_rt", "")
    if _at:
        st.query_params.clear()
        fake_hash = f"#access_token={_at}&refresh_token={_rt}"
        if _process_oauth_hash(auth, fake_hash):
            return True

    # 5. Mostrar formulário
    _render_form(auth, app_url)
    return False


# ── Formulário ─────────────────────────────────────────────────────────────────

def _render_form(auth: SupabaseAuth, app_url: str) -> None:
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    _, col, _ = st.columns([1.2, 2, 1.2])

    with col:
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

        tab_in, tab_up = st.tabs(["Entrar", "Criar Conta"])

        # ── Aba: Entrar ───────────────────────────────────────────────────────
        with tab_in:
            email_i = st.text_input("E-mail", key="li_email",
                                    placeholder="seu@email.com",
                                    label_visibility="collapsed")
            st.caption("E-mail")
            senha_i = st.text_input("Senha", key="li_senha", type="password",
                                    placeholder="••••••••",
                                    label_visibility="collapsed")
            st.caption("Senha")

            if st.button("Entrar", use_container_width=True,
                         type="primary", key="li_btn"):
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
                            _m = str(exc).lower()
                            if "invalid" in _m or "credentials" in _m:
                                st.error("E-mail ou senha incorretos.")
                            elif "email not confirmed" in _m:
                                st.warning("Confirme seu e-mail antes de entrar.")
                            else:
                                st.error(f"Erro ao entrar: {exc}")

            # ── Botão Google — <a> direto no Streamlit (sem iframe) ──────────
            # Usar st.markdown com <a target="_self"> garante navegação na
            # mesma aba sem passar por iframe (não há restrição de sandbox).
            if app_url:
                try:
                    _gurl = auth.google_auth_url(app_url)
                    st.markdown(
                        '<div class="or-divider"><hr><span>ou continue com</span><hr></div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<a href="{_gurl}" target="_self" class="g-oauth-btn">'
                        f'{_GOOGLE_SVG}&nbsp; Entrar com Google</a>',
                        unsafe_allow_html=True,
                    )
                except Exception:
                    st.caption("_(Google OAuth não configurado no Supabase)_")

        # ── Aba: Criar Conta ──────────────────────────────────────────────────
        with tab_up:
            st.caption("Apenas e-mails previamente autorizados podem criar conta.")
            nome_c   = st.text_input("Nome completo", key="su_nome",   placeholder="Seu nome")
            email_c  = st.text_input("E-mail",        key="su_email",  placeholder="seu@email.com")
            senha_c  = st.text_input("Senha",         key="su_senha",  type="password",
                                     placeholder="Mínimo 6 caracteres")
            senha_c2 = st.text_input("Confirmar senha", key="su_senha2", type="password",
                                     placeholder="Repita a senha")

            if st.button("Criar Conta", use_container_width=True,
                         type="primary", key="su_btn"):
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
                                "✅ Conta criada! Verifique seu e-mail para confirmar, "
                                "depois volte aqui para entrar."
                            )
                        except PermissionError as exc:
                            st.error(f"⛔ {exc}")
                        except Exception as exc:
                            _m = str(exc).lower()
                            if "already registered" in _m or "already exists" in _m:
                                st.warning("Este e-mail já existe. Use a aba Entrar.")
                            else:
                                st.error(f"Erro ao criar conta: {exc}")

        st.markdown(
            '<div class="login-footer">Problemas de acesso? '
            'Fale com o administrador do sistema.</div></div>',
            unsafe_allow_html=True,
        )


# ── Painel admin de emails ─────────────────────────────────────────────────────

def render_admin_panel(auth: SupabaseAuth) -> None:
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
