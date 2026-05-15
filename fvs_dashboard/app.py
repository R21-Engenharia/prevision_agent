"""
FVS Dashboard — Aplicacao Operacional de Qualidade
====================================================
Ponto de entrada principal.

Executar:
    streamlit run fvs_dashboard/app.py

    (a partir da raiz de prevision_agent/)
"""

import sys
from pathlib import Path

# Garante que prevision_agent/ esta no path para imports relativos
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv(_ROOT / ".env")

# ── Suporte a st.secrets (Streamlit Cloud) + .env (local) ────────────────────
def _secret(key: str, default: str = "") -> str:
    """Lê de st.secrets (cloud) ou os.getenv (local) com fallback."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

from fvs_dashboard.core.data_manager import DataManager, OBRAS
from fvs_dashboard.core.inmeta_client import InMetaClient

# ── Configuracao da pagina ────────────────────────────────────────────────────
st.set_page_config(
    page_title="FVS Dashboard — R21",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Sidebar */
    [data-testid="stSidebar"] { min-width: 260px; max-width: 260px; }
    [data-testid="stSidebar"] > div:first-child { background: #1a2744; }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span { color: #e8eaf0 !important; }
    [data-testid="stSidebar"] .stSelectbox label { color: #a0b0d0 !important; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }

    /* Topo */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }

    /* Metrics — cards com borda */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e0e6f0;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 1px 4px rgba(47,85,151,0.07);
    }
    [data-testid="stMetricLabel"] { font-size: 12px; font-weight: 600; color: #6b7fa3; text-transform: uppercase; letter-spacing: 0.4px; }
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: 700; color: #1a2744; }

    /* Secoes */
    h3 { color: #2F5597 !important; font-size: 15px !important; font-weight: 700 !important; margin-top: 1.2rem !important; }
    h1 { color: #1a2744 !important; }

    /* Badges de status */
    .badge-fin  { background:#E2EFDA; color:#375623; padding:3px 10px; border-radius:5px; font-weight:600; font-size:12px; }
    .badge-and  { background:#FFEB9C; color:#7F6000; padding:3px 10px; border-radius:5px; font-weight:600; font-size:12px; }
    .badge-nao  { background:#FFC7CE; color:#C00000; padding:3px 10px; border-radius:5px; font-weight:600; font-size:12px; }

    /* Dividers */
    hr { border: none; border-top: 1px solid #e8edf5; margin: 0.6rem 0; }

    /* Tabelas */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Auth Gate (Supabase) ──────────────────────────────────────────────────────
_SUPABASE_URL = _secret("SUPABASE_URL", "")
_SUPABASE_KEY = _secret("SUPABASE_KEY", "")

if _SUPABASE_URL and _SUPABASE_KEY:
    from fvs_dashboard.auth.supabase_auth import SupabaseAuth
    from fvs_dashboard.auth.login_ui import render_login_page

    if "auth_client" not in st.session_state:
        st.session_state.auth_client = SupabaseAuth(_SUPABASE_URL, _SUPABASE_KEY)

    _auth: SupabaseAuth = st.session_state.auth_client
    _APP_URL = _secret("APP_URL", "http://localhost:8501")

    if not render_login_page(_auth, _APP_URL):
        st.stop()
else:
    _auth = None  # Auth nao configurado — modo sem restricao (dev local)

# ── Session state ─────────────────────────────────────────────────────────────
# Recria DataManager se nao existir OU se for versao antiga (sem snapshot_info)
if "dm" not in st.session_state or not hasattr(st.session_state.dm, "snapshot_info"):
    st.session_state.dm = DataManager()
    st.session_state.snapshots_initialized = False  # forcca re-inicializacao
if "obra" not in st.session_state:
    st.session_state.obra = list(OBRAS.keys())[0]
if "snapshots_initialized" not in st.session_state:
    st.session_state.snapshots_initialized = False

dm: DataManager = st.session_state.dm

# ── Snapshot inicial automatico (retroativo com data de hoje) ─────────────────
if not st.session_state.snapshots_initialized:
    try:
        for _obra_name in OBRAS:
            dm.save_snapshot(_obra_name)  # no-op se ja existe hoje
        st.session_state.snapshots_initialized = True
    except Exception:
        st.session_state.snapshots_initialized = True  # nao travar o app

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏗️ FVS Dashboard")
    st.markdown("**R21 Empreendimentos**")
    st.divider()

    # Selecao de obra
    obra = st.selectbox(
        "**OBRA**",
        options=list(OBRAS.keys()),
        index=list(OBRAS.keys()).index(st.session_state.obra),
        key="obra_select",
    )
    if obra != st.session_state.obra:
        st.session_state.obra = obra

    st.divider()

    # Idade dos caches
    ages = dm.cache_age(obra)
    st.caption(f"Prevision: **{ages['prevision']}**")
    st.caption(f"InMeta:    **{ages['inmeta']}**")
    st.markdown("")

    # Info de snapshots
    snap_info = dm.snapshot_info(obra)
    if snap_info["n_snapshots"] > 0:
        st.caption(f"Snapshots: **{snap_info['n_snapshots']}** dias  |  Desde {snap_info['oldest']}")
    else:
        st.caption("Snapshots: aguardando primeiro registro")
    st.markdown("")

    # ── Autenticacao para atualizacoes ────────────────────────────────────────
    _REFRESH_PWD = _secret("REFRESH_PASSWORD", "r21qualidade")

    if "refresh_autenticado" not in st.session_state:
        st.session_state.refresh_autenticado = False

    if not st.session_state.refresh_autenticado:
        with st.expander("🔒 Atualizar dados (restrito)", expanded=False):
            _pwd_input = st.text_input("Senha", type="password", key="pwd_input",
                                       placeholder="Digite a senha...")
            if st.button("Entrar", use_container_width=True):
                if _pwd_input == _REFRESH_PWD:
                    st.session_state.refresh_autenticado = True
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
    else:
        # Botao: Atualizar InMeta (rapido)
        if st.button("🔄 Atualizar InMeta", use_container_width=True, type="primary"):
            with st.spinner("Conectando ao InMeta..."):
                try:
                    client = InMetaClient(
                        base_url=_secret("INMETA_BASE_URL", "https://api.inmeta.com.br"),
                        email=_secret("INMETA_EMAIL"),
                        senha=_secret("INMETA_SENHA"),
                    )
                    dm.refresh_inmeta(obra, client)
                    # Salva snapshot apos atualizar (max 1 por dia)
                    for _obra_name in OBRAS:
                        dm.save_snapshot(_obra_name)
                    st.success("Dados atualizados e snapshot salvo!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

        # Botao: Atualizar Prevision (lento)
        with st.expander("Atualizar Prevision (lento)"):
            st.warning("Coleta completa leva ~20 minutos.", icon="⏱️")
            confirma = st.checkbox("Confirmo que quero atualizar o Prevision")
            if st.button("🔄 Iniciar coleta Prevision", disabled=not confirma, use_container_width=True):
                st.info("Funcionalidade disponivel via linha de comando:\n`python collectors/operational_collector.py`")

        if st.button("🔓 Sair", use_container_width=True):
            st.session_state.refresh_autenticado = False
            st.rerun()

    st.divider()
    st.caption("Fase 6 — MVP Operacional")
    st.caption("Prevision + InMeta")

    # ── Usuario logado (apenas quando auth esta ativo) ────────────────────────
    if _auth is not None and "auth_email" in st.session_state:
        st.divider()
        _nome_display = st.session_state.get("auth_nome", st.session_state.get("auth_email", ""))
        st.markdown(
            f'<div style="font-size:11px;color:#8aa4cc;margin-bottom:2px;">👤 Logado como</div>'
            f'<div style="font-size:12px;font-weight:600;color:#c5d4ea;word-break:break-all;">'
            f'{_nome_display}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        if st.button("Sair", use_container_width=True, key="btn_logout_global"):
            _auth.logout()
            st.rerun()

    # ── Assinatura do desenvolvedor (rodape da sidebar) ──────────────────────
    st.markdown(
        """
        <div style="
            text-align: center;
            padding: 18px 0 8px 0;
        ">
            <div style="
                font-size: 9px;
                color: #566a8a;
                text-transform: uppercase;
                letter-spacing: 2px;
                font-weight: 600;
                margin-bottom: 4px;
            ">Desenvolvido por</div>
            <div style="
                font-size: 13px;
                font-weight: 700;
                color: #8aa4cc;
                letter-spacing: 1px;
            ">Elrik</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Navegacao por paginas ─────────────────────────────────────────────────────
_pages = [
    st.Page("pages/1_Visao_Geral.py",            title="Visao Geral",        icon="📊"),
    st.Page("pages/2_Backlog_FVS.py",            title="Backlog FVS",        icon="📋"),
    st.Page("pages/3_Pendentes.py",              title="Pendentes",          icon="🔴"),
    st.Page("pages/4_Exportar.py",               title="Exportar",           icon="⬇️"),
    st.Page("pages/5_Auditoria_Gerencial.py",    title="Auditoria Gerencial", icon="📈"),
]

# Pagina de gestao de usuarios — apenas para admins autenticados
if _auth is not None and st.session_state.get("auth_role") == "admin":
    _pages.append(
        st.Page("pages/6_Usuarios.py", title="Usuarios", icon="👥")
    )

pg = st.navigation(_pages, position="sidebar")

pg.run()
