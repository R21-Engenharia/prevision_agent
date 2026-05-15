"""
Pagina 6 — Gestao de Usuarios Autorizados (acesso restrito via senha).
"""
import streamlit as st

# Guard — so aparece no menu quando o painel restrito esta desbloqueado
if not st.session_state.get("refresh_autenticado"):
    st.error("🔒 Acesso restrito. Desbloqueie o painel de dados na barra lateral.")
    st.stop()

if "auth_client" not in st.session_state:
    st.error("Autenticacao nao inicializada.")
    st.stop()

from fvs_dashboard.auth.login_ui import render_admin_panel

st.title("👥 Usuarios Autorizados")
st.caption("Gerencie quais e-mails podem acessar o FVS Dashboard.")
st.divider()

render_admin_panel(st.session_state.auth_client)
