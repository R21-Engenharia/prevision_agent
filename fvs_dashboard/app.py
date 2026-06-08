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

# ── Tema: claro / escuro ──────────────────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "light"

_DARK = st.session_state.theme == "dark"

# Variáveis de cor por tema
_BG        = "#111111" if _DARK else "#F7F7F7"
_CARD_BG   = "#1E1E1E" if _DARK else "#FFFFFF"
_CARD_BRD  = "#333333" if _DARK else "#E8E8E8"
_TEXT_PRI  = "#FFFFFF"  if _DARK else "#1A1A1A"
_TEXT_SEC  = "#AAAAAA" if _DARK else "#888888"
_DIVIDER   = "#2E2E2E" if _DARK else "#E8E8E8"
_EXP_BG    = "#2A2A2A" if _DARK else "#FFFFFF"

# ── CSS global — Paleta R21 Empreendimentos ───────────────────────────────────
st.markdown(f"""
<style>
    /* ── Sidebar — sempre escura ─────────────────────────────────────────── */
    [data-testid="stSidebar"] {{ min-width: 260px; max-width: 260px; }}
    [data-testid="stSidebar"] > div:first-child {{
        background: #1A1A1A;
        border-right: 3px solid #C41230;
    }}
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {{ color: #e8e8e8 !important; }}
    [data-testid="stSidebar"] .stSelectbox label {{
        color: #aaaaaa !important; font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.5px;
    }}
    [data-testid="stSidebar"] a {{ color: #e8e8e8 !important; text-decoration: none !important; }}
    [data-testid="stSidebar"] [aria-selected="true"],
    [data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{
        background: #C41230 !important; border-radius: 6px; color: #ffffff !important;
    }}
    [data-testid="stSidebar"] .stButton > button {{
        background: #C41230 !important; color: #ffffff !important;
        border: none !important; font-weight: 600 !important; border-radius: 6px !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{ background: #a50e27 !important; }}
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
        background: #2e2e2e !important; color: #cccccc !important; border: 1px solid #444 !important;
    }}

    /* ── Sidebar: remove botao de recolher (sidebar sempre aberta) ──────── */
    [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
    [data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}

    /* ── Esconde link GitHub / Manage app / rodape do Streamlit Cloud ────── */
    footer                                   {{ visibility: hidden; }}
    [data-testid="stStatusWidget"]           {{ display: none !important; }}
    [data-testid="stDeployButton"]           {{ display: none !important; }}
    .stDeployButton                          {{ display: none !important; }}
    iframe[title="streamlit_analytics"]      {{ display: none !important; }}

    /* ── Layout ──────────────────────────────────────────────────────────── */
    .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}
    body, .stApp, .main {{ background-color: {_BG} !important; }}

    /* ── Metric cards ────────────────────────────────────────────────────── */
    [data-testid="stMetric"] {{
        background: {_CARD_BG} !important;
        border: 1px solid {_CARD_BRD} !important;
        border-top: 3px solid #C41230 !important;
        border-radius: 8px;
        padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(196,18,48,0.08);
    }}
    [data-testid="stMetricLabel"] {{
        font-size: 11px; font-weight: 700; color: {_TEXT_SEC} !important;
        text-transform: uppercase; letter-spacing: 0.5px;
    }}
    [data-testid="stMetricValue"] {{ font-size: 28px; font-weight: 800; color: {_TEXT_PRI} !important; }}
    [data-testid="stMetricDelta"] {{ font-size: 12px; font-weight: 600; }}

    /* ── Titulos ─────────────────────────────────────────────────────────── */
    h1 {{ color: {_TEXT_PRI} !important; font-weight: 800 !important; }}
    h2 {{ color: {_TEXT_PRI} !important; font-weight: 700 !important; }}
    h3 {{
        color: #C41230 !important; font-size: 14px !important;
        font-weight: 700 !important; text-transform: uppercase !important;
        letter-spacing: 0.5px !important; margin-top: 1.2rem !important;
    }}
    p, li, span {{ color: {_TEXT_PRI}; }}

    /* ── Botoes primarios globais ────────────────────────────────────────── */
    .stButton > button[kind="primary"] {{
        background: #C41230 !important; color: #ffffff !important;
        border: none !important; border-radius: 6px !important; font-weight: 600 !important;
    }}
    .stButton > button[kind="primary"]:hover {{ background: #a50e27 !important; }}

    /* ── Tabs ────────────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{ border-bottom: 2px solid {_DIVIDER}; gap: 4px; }}
    .stTabs [data-baseweb="tab"] {{ color: {_TEXT_SEC} !important; font-weight: 600; }}
    .stTabs [aria-selected="true"] {{
        color: #C41230 !important; border-bottom: 2px solid #C41230 !important;
        background: transparent !important;
    }}

    /* ── Badges de status ────────────────────────────────────────────────── */
    .badge-fin {{ background:#E8F5E9; color:#2E7D32; padding:3px 10px; border-radius:5px; font-weight:600; font-size:12px; }}
    .badge-and {{ background:#FFF8E1; color:#F57F17; padding:3px 10px; border-radius:5px; font-weight:600; font-size:12px; }}
    .badge-nao {{ background:#FFEBEE; color:#C41230; padding:3px 10px; border-radius:5px; font-weight:600; font-size:12px; }}

    /* ── Dividers e tabelas ──────────────────────────────────────────────── */
    hr {{ border: none; border-top: 1px solid {_DIVIDER}; margin: 0.6rem 0; }}
    .stDataFrame {{ border-radius: 8px; overflow: hidden; }}

    /* ── Expanders ───────────────────────────────────────────────────────── */
    [data-testid="stExpander"] {{ background: {_EXP_BG} !important; border-radius: 8px; }}
    [data-testid="stExpander"] summary {{ font-weight: 600; color: {_TEXT_PRI} !important; }}

    /* ── Inputs e selects ────────────────────────────────────────────────── */
    [data-testid="stSelectbox"] > div > div {{
        background: {_CARD_BG} !important; color: {_TEXT_PRI} !important;
    }}
</style>
""", unsafe_allow_html=True)

# ── Auth Gate (Supabase) ──────────────────────────────────────────────────────
_SUPABASE_URL = _secret("SUPABASE_URL", "")
_SUPABASE_KEY = _secret("SUPABASE_KEY", "")

if _SUPABASE_URL and _SUPABASE_KEY:
    from fvs_dashboard.auth.supabase_auth import SupabaseAuth
    from fvs_dashboard.auth.login_ui import render_login_page

    _ALLOWED_DOMAINS = _secret("ALLOWED_DOMAINS", "")

    # Recria o client se estiver desatualizado (deploy novo com métodos novos)
    if "auth_client" not in st.session_state or \
       not hasattr(st.session_state.auth_client, "get_session_tokens"):
        st.session_state.auth_client = SupabaseAuth(
            _SUPABASE_URL, _SUPABASE_KEY,
            allowed_domains=_ALLOWED_DOMAINS,
        )

    _auth: SupabaseAuth = st.session_state.auth_client
    _APP_URL = _secret("APP_URL", "http://localhost:8501")

    if not render_login_page(_auth, _APP_URL):
        st.stop()
else:
    _auth = None  # Auth nao configurado — modo sem restricao (dev local)

# ── Session state ─────────────────────────────────────────────────────────────
# Recria DataManager se nao existir OU se for versao antiga (sem uses_supabase)
if "dm" not in st.session_state or not hasattr(st.session_state.dm, "uses_supabase"):
    st.session_state.dm = DataManager()
    st.session_state.snapshots_initialized = False
if "obra" not in st.session_state:
    st.session_state.obra = list(OBRAS.keys())[0]
if "snapshots_initialized" not in st.session_state:
    st.session_state.snapshots_initialized = False

dm: DataManager = st.session_state.dm

# ── Ativa persistencia Supabase (uma vez por sessao) ──────────────────────────
if not getattr(dm, "uses_supabase", False):
    _sb_url = _secret("SUPABASE_URL", "")
    _sb_key = _secret("SUPABASE_KEY", "")
    if _sb_url and _sb_key:
        try:
            dm.setup_supabase(_sb_url, _sb_key)
        except Exception:
            pass  # sem Supabase: continua com Parquet local (dev)

# ── Auto-refresh InMeta — roda sempre ao abrir nova sessao ────────────────────
# auto_refresh_done garante que executa uma unica vez por sessao de browser,
# nao a cada navegacao entre paginas. Sempre busca dados frescos do InMeta.

if "auto_refresh_done" not in st.session_state:
    _ar_ph = st.empty()
    _ar_ph.info("⏳ Buscando dados atualizados do InMeta...")
    try:
        _ar_client = InMetaClient(
            base_url=_secret("INMETA_BASE_URL", "https://api.inmeta.com.br"),
            email   =_secret("INMETA_EMAIL"),
            senha   =_secret("INMETA_SENHA"),
        )
        for _obra_name in OBRAS:
            dm.refresh_inmeta(_obra_name, _ar_client)
            dm.save_snapshot(_obra_name)  # persiste historico no Supabase
        _ar_ph.empty()
        st.session_state["auto_refresh_done"] = True
        st.session_state["auto_refresh_ok"]   = True
        st.rerun()
    except Exception as _ar_err:
        _ar_ph.warning(
            f"⚠️ Nao foi possivel atualizar o InMeta: {_ar_err}. "
            "Os dados exibidos podem estar desatualizados."
        )
        st.session_state["auto_refresh_done"] = True
        st.session_state["auto_refresh_ok"]   = False

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Logo ──────────────────────────────────────────────────────────────────
    _LOGO_PATH = Path(__file__).parent / "assets" / "r21_logo.png"
    if _LOGO_PATH.exists():
        st.image(str(_LOGO_PATH), width=170)
        st.markdown(
            '<div style="font-size:13px; font-weight:700; color:#ffffff; '
            'margin: 4px 0 0 2px;">FVS Dashboard</div>'
            '<div style="font-size:10px; color:#888888; margin-bottom:4px;">Portal de Qualidade</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="padding: 4px 0 8px 0;">
                <div style="font-size:10px; font-weight:700; color:#C41230;
                            text-transform:uppercase; letter-spacing:2.5px; margin-bottom:2px;">
                    R21 Empreendimentos
                </div>
                <div style="font-size:18px; font-weight:800; color:#ffffff; letter-spacing:-0.3px;">
                    🏗️ FVS Dashboard
                </div>
                <div style="font-size:10px; color:#888888; margin-top:2px;">
                    Portal de Qualidade
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Toggle claro / escuro ─────────────────────────────────────────────────
    _t1, _t2 = st.columns(2)
    with _t1:
        if st.button("☀️ Claro",  use_container_width=True,
                     type="primary" if not _DARK else "secondary", key="btn_light"):
            st.session_state.theme = "light"
            st.rerun()
    with _t2:
        if st.button("🌙 Escuro", use_container_width=True,
                     type="primary" if _DARK else "secondary", key="btn_dark"):
            st.session_state.theme = "dark"
            st.rerun()

    st.markdown(
        '<hr style="border-top:1px solid #333333; margin: 8px 0 12px 0;">',
        unsafe_allow_html=True,
    )

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
    ages        = dm.cache_age(obra)
    _imeta_h    = dm.inmeta_age_hours()
    _dot        = "🟢" if (_imeta_h is not None and _imeta_h < 6)  else \
                  "🟡" if (_imeta_h is not None and _imeta_h < 24) else "🔴"
    st.caption(f"Prevision: **{ages['prevision']}**")
    st.caption(f"InMeta: {_dot} **{ages['inmeta']}**")
    _ar_ok = st.session_state.get("auto_refresh_ok")
    if _ar_ok is True:
        st.caption("✅ Auto-refresh OK nesta sessao")
    elif _ar_ok is False:
        st.caption("❌ Auto-refresh falhou — atualize manualmente")
    else:
        st.caption("↻ Auto-atualiza se dados > 8h")
    st.markdown("")

    # Info de snapshots
    snap_info = dm.snapshot_info(obra)
    if snap_info["n_snapshots"] > 0:
        st.caption(f"Snapshots: **{snap_info['n_snapshots']}** dias  |  Desde {snap_info['oldest']}")
    else:
        st.caption("Snapshots: aguardando primeiro registro")
    st.markdown("")

    # ── Autenticacao para atualizacoes ────────────────────────────────────────
    _is_admin  = st.session_state.get("auth_role") == "admin"
    _is_viewer = st.session_state.get("auth_role") in ("viewer", "admin")

    # ── Atualizar InMeta — disponível para todos (viewer + admin) ─────────────
    if _is_viewer:
        if st.button("🔄 Atualizar InMeta", use_container_width=True, type="primary"):
            with st.spinner("Conectando ao InMeta..."):
                try:
                    client = InMetaClient(
                        base_url=_secret("INMETA_BASE_URL", "https://api.inmeta.com.br"),
                        email=_secret("INMETA_EMAIL"),
                        senha=_secret("INMETA_SENHA"),
                    )
                    dm.refresh_inmeta(obra, client)
                    for _obra_name in OBRAS:
                        dm.save_snapshot(_obra_name)
                    st.success("Dados atualizados!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

    # ── Atualizar Prevision — somente admin ───────────────────────────────────
    if _is_admin:
        with st.expander("Atualizar Prevision (lento)"):
            st.warning("Coleta completa leva ~20 minutos.", icon="⏱️")
            confirma = st.checkbox("Confirmo que quero atualizar o Prevision")
            if st.button("🔄 Iniciar coleta Prevision",
                         disabled=not confirma, use_container_width=True):
                st.info("Funcionalidade disponivel via linha de comando:\n"
                        "`python collectors/operational_collector.py`")

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
            # Sinaliza limpeza do localStorage na próxima renderização do login
            st.session_state["_pending_clear_tokens"] = True
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
    st.Page("pages/7_Tempo.py",                  title="Condicao do Tempo",  icon="🌤️"),
    st.Page("pages/8_Decoracao.py",              title="Decoracao",          icon="🏛️"),
]

# Pagina de gestao de usuarios — somente admins
if _auth is not None and st.session_state.get("auth_role") == "admin":
    _pages.append(
        st.Page("pages/6_Usuarios.py", title="Usuarios", icon="👥")
    )

pg = st.navigation(_pages, position="sidebar")

pg.run()
