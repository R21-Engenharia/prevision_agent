"""
Pagina 6 — Gestao de Usuarios Autorizados (somente admins).
"""
import streamlit as st

# Guard — so admins chegam aqui
if st.session_state.get("auth_role") != "admin":
    st.error("Acesso restrito a administradores.")
    st.stop()

if "auth_client" not in st.session_state:
    st.error("Autenticacao nao inicializada.")
    st.stop()

from fvs_dashboard.auth.login_ui import render_admin_panel

st.title("👥 Usuarios Autorizados")
st.caption("Gerencie quais e-mails podem acessar o FVS Dashboard.")
st.divider()

render_admin_panel(st.session_state.auth_client)
