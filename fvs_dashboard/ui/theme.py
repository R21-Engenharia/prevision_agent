"""
theme.py — Design System "R21 Quality Instrument"
==================================================
Tokens, CSS global e componentes de UI reutilizaveis.

Direcao de design: um painel de instrumentacao de engenharia — preciso,
gridado, calmo e orientado a dados. O vermelho R21 (#C41230) e a cor-sinal
(marca + atencao) sobre um sistema neutro disciplinado. Tipografia
Space Grotesk (titulos/numeros) + Inter (corpo/UI).

API publica:
    inject_theme(dark)          -> injeta o CSS global (chamar 1x em app.py)
    page_header(title, ...)     -> masthead de instrumento (topo de cada pagina)
    section(label)              -> cabecalho de secao consistente
    kpi(label, value, ...)      -> HTML de um KPI card (usar com st.markdown)
    kpi_row(cards)              -> HTML de uma linha de KPI cards
    badge(text, tone)           -> HTML de um badge de status
    plotly_layout(dark, ...)    -> dict para fig.update_layout consistente
    style_fig(fig, dark)        -> aplica o layout padrao a uma figura Plotly
    STATUS, SERIES, GANTT_STATUS, tokens()  -> constantes de cor
    PLOTLY_CONFIG               -> config padrao do st.plotly_chart
"""
from __future__ import annotations

from string import Template
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# 1. TOKENS
# ─────────────────────────────────────────────────────────────────────────────

_LIGHT = {
    "canvas":       "#F4F6F9",
    "surface":      "#FFFFFF",
    "surface2":     "#EDF1F6",
    "border":       "#E2E7EE",
    "border_strong":"#CFD6E0",
    "ink":          "#171A1F",
    "slate":        "#5C6572",
    "muted":        "#909AA7",
    "brand":        "#C41230",
    "brand_hover":  "#A50E27",
    "brand_ink":    "#C41230",
    "brand_soft":   "rgba(196,18,48,0.07)",
    "shadow":       "0 1px 2px rgba(16,24,40,0.04), 0 4px 16px rgba(16,24,40,0.05)",
    "shadow_hover": "0 2px 4px rgba(16,24,40,0.06), 0 10px 28px rgba(16,24,40,0.10)",
    "grid":         "rgba(23,26,31,0.07)",
}

_DARK = {
    "canvas":       "#0F1319",
    "surface":      "#171C23",
    "surface2":     "#1F2630",
    "border":       "#2A313C",
    "border_strong":"#3A424E",
    "ink":          "#E9EDF2",
    "slate":        "#9AA4B2",
    "muted":        "#6B7480",
    "brand":        "#C41230",
    "brand_hover":  "#D8324D",
    "brand_ink":    "#F1637A",
    "brand_soft":   "rgba(226,58,87,0.12)",
    "shadow":       "0 1px 2px rgba(0,0,0,0.30), 0 4px 16px rgba(0,0,0,0.35)",
    "shadow_hover": "0 2px 4px rgba(0,0,0,0.35), 0 12px 30px rgba(0,0,0,0.50)",
    "grid":         "rgba(233,237,242,0.08)",
}

# ── Cores semanticas de status (usadas em badges E graficos) ──────────────────
# Consistentes em toda a aplicacao. Em FVS, "Nao Iniciada" e o alerta (vermelho).
STATUS = {
    "fin":     "#1E8E5A",   # Finalizada / positivo — esmeralda
    "and":     "#D98A00",   # Em Andamento — ambar
    "nao":     "#C41230",   # Nao Iniciada — vermelho R21 (atencao)
    "neutral": "#8A94A6",   # neutro / outros
    "crit":    "#C41230",   # critico
}

# ── Series de dados (comparativos) ────────────────────────────────────────────
SERIES = {
    "a":   "#C41230",   # Cape Town / serie primaria
    "b":   "#3E6DA8",   # Holmes / serie secundaria
    "sun": "#E39A2B",   # Ensolarado
    "cloud":"#7C97B8",  # Nublado
    "rain":"#3E6DA8",   # Chuvoso
}

# ── Status do modulo Decoracao (labels proprios) ──────────────────────────────
GANTT_STATUS = {
    "Finalizada":   "#1E8E5A",
    "Em andamento": "#D98A00",
    "Nao iniciada": "#8A94A6",
    "Atrasada":     "#C41230",
}

FONT_STACK    = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
DISPLAY_STACK = "'Space Grotesk', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif"

PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "select2d", "lasso2d",
        "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d",
    ],
}


def tokens(dark: bool | None = None) -> dict:
    """Retorna o dicionario de tokens do tema atual (ou do tema informado)."""
    if dark is None:
        dark = st.session_state.get("theme", "light") == "dark"
    return _DARK if dark else _LIGHT


# ─────────────────────────────────────────────────────────────────────────────
# 2. CSS GLOBAL
# ─────────────────────────────────────────────────────────────────────────────

_CSS = Template("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

/* ── Base ─────────────────────────────────────────────────────────────────── */
:root { --r21-brand: $brand; --r21-ink: $ink; }
html, body, .stApp, [class*="css"] { font-family: $font; }
.stApp, body, .main { background: $canvas !important; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1400px; }

p, li, span, label, div, td, th { color: $ink; }
a { color: $brand_ink; }

h1, h2, h3, h4 { font-family: $display; letter-spacing: -0.01em; color: $ink !important; }
h1 { font-weight: 700 !important; }
h2 { font-weight: 600 !important; }

/* Neutraliza os h3 (###) — paginas usam ui.section() no lugar */
.main h3 { font-size: 1.05rem !important; font-weight: 600 !important;
           color: $ink !important; text-transform: none !important;
           letter-spacing: -0.01em !important; }

/* Esconde cromo do Streamlit Cloud */
footer                              { visibility: hidden; }
[data-testid="stStatusWidget"]      { display: none !important; }
[data-testid="stDeployButton"],
.stDeployButton                     { display: none !important; }
#MainMenu                           { visibility: hidden; }

/* ── Masthead de instrumento (page_header) ────────────────────────────────── */
.r21-mast { margin: 0 0 1.4rem 0; }
.r21-mast-top { display: flex; align-items: flex-start; gap: 14px; }
.r21-mast-tick { width: 4px; align-self: stretch; min-height: 44px;
                 background: $brand; border-radius: 3px; flex-shrink: 0; }
.r21-mast-body { flex: 1; min-width: 0; }
.r21-eyebrow { font-family: $font; font-size: 11px; font-weight: 600;
               text-transform: uppercase; letter-spacing: 0.14em;
               color: $brand_ink; margin-bottom: 3px; }
.r21-mast h1 { font-family: $display; font-size: 27px; font-weight: 700;
               line-height: 1.1; margin: 0; color: $ink; letter-spacing: -0.02em; }
.r21-mast-sub { font-size: 13.5px; color: $slate; margin-top: 5px; line-height: 1.4; }
.r21-mast-chip { font-family: $font; font-size: 12px; font-weight: 600;
                 color: $slate; background: $surface; border: 1px solid $border;
                 border-radius: 999px; padding: 5px 13px; white-space: nowrap;
                 flex-shrink: 0; }
.r21-mast-rule { height: 1px; background: $border; margin-top: 14px; }

/* ── Section header ───────────────────────────────────────────────────────── */
.r21-section { display: flex; align-items: center; gap: 9px;
               margin: 1.9rem 0 0.9rem 0; }
.r21-section::before { content: ""; width: 3px; height: 15px; border-radius: 2px;
                       background: $brand; flex-shrink: 0; }
.r21-section-label { font-family: $display; font-size: 13px; font-weight: 600;
                     letter-spacing: 0.02em; color: $ink; }
.r21-section-line { flex: 1; height: 1px; background: $border; }

/* ── KPI readout cards ────────────────────────────────────────────────────── */
.r21-kpi { position: relative; background: $surface; border: 1px solid $border;
           border-radius: 12px; padding: 15px 17px 16px; overflow: hidden;
           box-shadow: $shadow; transition: transform .14s ease, box-shadow .14s ease;
           height: 100%; }
.r21-kpi:hover { transform: translateY(-2px); box-shadow: $shadow_hover; }
.r21-kpi-bar { position: absolute; left: 0; bottom: 0; height: 3px; width: 100%; }
.r21-kpi-label { font-family: $font; font-size: 10.5px; font-weight: 600;
                 text-transform: uppercase; letter-spacing: 0.06em;
                 color: $slate; margin-bottom: 7px; }
.r21-kpi-value { font-family: $display; font-size: 30px; font-weight: 700;
                 line-height: 1; color: $ink; font-variant-numeric: tabular-nums; }
.r21-kpi-sub { font-size: 12px; color: $muted; margin-top: 7px; line-height: 1.35; }
.r21-kpi-delta { font-size: 12px; font-weight: 600; margin-top: 7px; }

/* ── Badges ───────────────────────────────────────────────────────────────── */
.r21-badge { display: inline-flex; align-items: center; gap: 5px;
             font-family: $font; font-size: 11.5px; font-weight: 600;
             padding: 3px 10px; border-radius: 6px; line-height: 1.5; }

/* ── st.metric nativo (fallback consistente) ──────────────────────────────── */
[data-testid="stMetric"] { background: $surface; border: 1px solid $border;
    border-radius: 12px; padding: 14px 18px 16px; box-shadow: $shadow; }
[data-testid="stMetricLabel"] { font-size: 10.5px; font-weight: 600;
    color: $slate !important; text-transform: uppercase; letter-spacing: 0.06em; }
[data-testid="stMetricLabel"] p { color: $slate !important; }
[data-testid="stMetricValue"] { font-family: $display; font-size: 28px;
    font-weight: 700; color: $ink !important; font-variant-numeric: tabular-nums; }
[data-testid="stMetricDelta"] { font-size: 12px; font-weight: 600; }

/* ── Alert boxes (info/warning/success/error) ─────────────────────────────── */
[data-testid="stAlert"] { border-radius: 10px; border: 1px solid $border; }

/* ── Botoes ───────────────────────────────────────────────────────────────── */
.stButton > button { border-radius: 9px !important; font-weight: 600 !important;
    font-family: $font !important; transition: all .13s ease; }
.stButton > button[kind="primary"] { background: $brand !important;
    color: #fff !important; border: 1px solid $brand !important;
    box-shadow: 0 1px 2px rgba(196,18,48,0.20); }
.stButton > button[kind="primary"]:hover { background: $brand_hover !important;
    border-color: $brand_hover !important; transform: translateY(-1px); }
.stButton > button[kind="secondary"] { background: $surface !important;
    color: $ink !important; border: 1px solid $border_strong !important; }
.stButton > button[kind="secondary"]:hover { border-color: $brand !important;
    color: $brand_ink !important; }
.stDownloadButton > button { border-radius: 9px !important; font-weight: 600 !important;
    border: 1px solid $border_strong !important; }

/* ── Inputs / selects ─────────────────────────────────────────────────────── */
[data-baseweb="input"], [data-baseweb="select"] > div,
.stTextInput input, .stNumberInput input {
    border-radius: 9px !important; }
.stTextInput input, .stNumberInput input, [data-baseweb="select"] > div {
    background: $surface !important; border-color: $border !important;
    color: $ink !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {
    border-color: $brand !important; box-shadow: 0 0 0 3px $brand_soft !important; }
.stTextInput label, .stSelectbox label, .stDateInput label,
.stRadio label, .stMultiSelect label, .stNumberInput label {
    font-size: 12px !important; font-weight: 600 !important; color: $slate !important; }

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid $border; gap: 6px; }
.stTabs [data-baseweb="tab"] { color: $slate !important; font-weight: 600;
    font-family: $font; }
.stTabs [aria-selected="true"] { color: $brand_ink !important;
    border-bottom: 2px solid $brand !important; background: transparent !important; }

/* ── Radio horizontal (chips) ─────────────────────────────────────────────── */
.stRadio [role="radiogroup"] { gap: 4px; }

/* ── Dataframes / tabelas ─────────────────────────────────────────────────── */
[data-testid="stDataFrame"] { border: 1px solid $border; border-radius: 10px;
    overflow: hidden; }
[data-testid="stDataFrame"] thead th { background: $surface2 !important;
    text-transform: uppercase; font-size: 10.5px !important; letter-spacing: 0.04em;
    color: $slate !important; font-weight: 600 !important; }

/* ── Expanders ────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] { background: $surface !important; border: 1px solid $border !important;
    border-radius: 10px !important; box-shadow: none; }
[data-testid="stExpander"] summary { font-weight: 600; color: $ink !important;
    font-family: $font; }
[data-testid="stExpander"] summary:hover { color: $brand_ink !important; }

/* ── Dividers ─────────────────────────────────────────────────────────────── */
hr { border: none; border-top: 1px solid $border; margin: 0.6rem 0; }
[data-testid="stCaptionContainer"], .stCaption, [data-testid="stCaptionContainer"] p {
    color: $muted !important; }

/* ── Sidebar — ancora escura de comando ───────────────────────────────────── */
[data-testid="stSidebar"] { min-width: 268px; max-width: 268px; }
[data-testid="stSidebar"] > div:first-child { background: #14171C;
    border-right: 1px solid #23272E; }
[data-testid="stSidebar"] * { color: #D6DBE2; }
[data-testid="stSidebar"] .r21-side-brand { color: #fff; }
[data-testid="stSidebar"] .r21-side-tag { color: $brand_ink; }
[data-testid="stSidebar"] .r21-side-muted { color: #7C8694; }
[data-testid="stSidebar"] label { color: #8B95A3 !important; font-size: 10.5px !important;
    text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600 !important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div { background: #1E232B !important;
    border-color: #2C323B !important; color: #E7EBF0 !important; }
[data-testid="stSidebar"] a { color: #C3CAD4 !important; text-decoration: none !important;
    border-radius: 8px; }
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] { border-radius: 8px; }
[data-testid="stSidebar"] [aria-current="page"],
[data-testid="stSidebar"] [aria-selected="true"] {
    background: $brand !important; color: #fff !important; border-radius: 8px; }
[data-testid="stSidebar"] [aria-current="page"] * { color: #fff !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"] { background: $brand !important;
    border-color: $brand !important; }
[data-testid="stSidebar"] .stButton > button[kind="secondary"] { background: #1E232B !important;
    color: #C3CAD4 !important; border: 1px solid #2C323B !important; }
[data-testid="stSidebar"] hr { border-top-color: #23272E; }
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"] { display: none !important; }

/* ── Acessibilidade ───────────────────────────────────────────────────────── */
:focus-visible { outline: 2px solid $brand !important; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
    * { transition: none !important; animation: none !important; }
    .r21-kpi:hover { transform: none; }
}

/* ── Responsivo ───────────────────────────────────────────────────────────── */
@media (max-width: 640px) {
    .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
    .r21-mast h1 { font-size: 22px; }
    .r21-mast-chip { display: none; }
    .r21-kpi-value { font-size: 26px; }
}
</style>
""")


def inject_theme(dark: bool | None = None) -> None:
    """Injeta o CSS global do design system. Chamar uma vez em app.py."""
    t = dict(tokens(dark))
    t["font"] = FONT_STACK
    t["display"] = DISPLAY_STACK
    st.markdown(_CSS.substitute(t), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPONENTES
# ─────────────────────────────────────────────────────────────────────────────

def _esc(s) -> str:
    import html
    return html.escape(str(s), quote=True)


def page_header(title: str, *, eyebrow: str = "", subtitle: str = "",
                chip: str = "") -> None:
    """Masthead de instrumento — cabecalho padrao no topo de cada pagina."""
    eyebrow_html = f'<div class="r21-eyebrow">{_esc(eyebrow)}</div>' if eyebrow else ""
    sub_html     = f'<div class="r21-mast-sub">{_esc(subtitle)}</div>' if subtitle else ""
    chip_html    = f'<div class="r21-mast-chip">{_esc(chip)}</div>' if chip else ""
    st.markdown(
        f'<div class="r21-mast"><div class="r21-mast-top">'
        f'<div class="r21-mast-tick"></div>'
        f'<div class="r21-mast-body">{eyebrow_html}'
        f'<h1>{_esc(title)}</h1>{sub_html}</div>'
        f'{chip_html}</div><div class="r21-mast-rule"></div></div>',
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    """Cabecalho de secao consistente (substitui st.markdown('### ...'))."""
    st.markdown(
        f'<div class="r21-section"><span class="r21-section-label">{_esc(label)}</span>'
        f'<span class="r21-section-line"></span></div>',
        unsafe_allow_html=True,
    )


# tom -> cor de destaque do card
_TONES = {
    "brand":   STATUS["nao"],
    "fin":     STATUS["fin"],
    "and":     STATUS["and"],
    "nao":     STATUS["nao"],
    "neutral": STATUS["neutral"],
    "info":    SERIES["b"],
}


def kpi(label: str, value, *, sub: str = "", tone: str = "brand",
        delta: str = "", delta_tone: str = "") -> str:
    """Retorna o HTML de um KPI card. Renderizar com st.markdown(..., unsafe_allow_html=True)."""
    accent = _TONES.get(tone, _TONES["brand"])
    sub_html = f'<div class="r21-kpi-sub">{sub}</div>' if sub else ""
    delta_html = ""
    if delta:
        dc = _TONES.get(delta_tone, STATUS["neutral"]) if delta_tone else STATUS["neutral"]
        delta_html = f'<div class="r21-kpi-delta" style="color:{dc}">{delta}</div>'
    return (
        f'<div class="r21-kpi">'
        f'<div class="r21-kpi-bar" style="background:{accent}"></div>'
        f'<div class="r21-kpi-label">{_esc(label)}</div>'
        f'<div class="r21-kpi-value">{_esc(value)}</div>'
        f'{sub_html}{delta_html}</div>'
    )


def kpi_row(cards: list[str], gap: str = "12px") -> None:
    """Renderiza uma linha responsiva de KPI cards (lista de HTML de kpi())."""
    inner = "".join(f'<div style="flex:1;min-width:150px">{c}</div>' for c in cards)
    st.markdown(
        f'<div style="display:flex;gap:{gap};flex-wrap:wrap;margin:2px 0 4px">{inner}</div>',
        unsafe_allow_html=True,
    )


_BADGE_TONES = {
    "fin":     ("rgba(30,142,90,0.13)",  "#1E8E5A"),
    "and":     ("rgba(217,138,0,0.14)",  "#B67400"),
    "nao":     ("rgba(196,18,48,0.10)",  "#C41230"),
    "neutral": ("rgba(138,148,166,0.15)","#5C6572"),
}


def badge(text: str, tone: str = "neutral") -> str:
    """Retorna HTML de um badge de status."""
    bg, fg = _BADGE_TONES.get(tone, _BADGE_TONES["neutral"])
    return f'<span class="r21-badge" style="background:{bg};color:{fg}">{_esc(text)}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# 4. PLOTLY — chrome consistente
# ─────────────────────────────────────────────────────────────────────────────

def plotly_layout(dark: bool | None = None, *, height: int | None = None,
                  legend: bool = True, **overrides) -> dict:
    """Dict de layout padrao para figuras Plotly (fonte, cores, grid, margens)."""
    t = tokens(dark)
    layout = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_STACK, size=12, color=t["slate"]),
        margin=dict(l=10, r=10, t=16, b=10),
        colorway=[STATUS["nao"], SERIES["b"], STATUS["fin"], STATUS["and"],
                  STATUS["neutral"], "#9B59B6"],
        xaxis=dict(gridcolor=t["grid"], zerolinecolor=t["grid"],
                   tickfont=dict(size=11, color=t["slate"]), title_font=dict(size=11)),
        yaxis=dict(gridcolor=t["grid"], zerolinecolor=t["grid"],
                   tickfont=dict(size=11, color=t["slate"]), title_font=dict(size=11)),
        hoverlabel=dict(bgcolor=t["ink"], font_color=t["surface"],
                        font_family=FONT_STACK, font_size=12,
                        bordercolor=t["ink"]),
    )
    if height is not None:
        layout["height"] = height
    if legend:
        layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.02,
                                xanchor="left", x=0, font=dict(size=11, color=t["slate"]),
                                title_text="")
    else:
        layout["showlegend"] = False
    layout.update(overrides)
    return layout


def style_fig(fig, dark: bool | None = None, **kw):
    """Aplica plotly_layout() a uma figura e a devolve."""
    fig.update_layout(**plotly_layout(dark, **kw))
    return fig
