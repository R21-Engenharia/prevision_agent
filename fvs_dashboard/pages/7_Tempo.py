"""
Pagina 7 — Condicao do Tempo
============================
Dados do Diario de Obra via API InMeta.
Endpoint: GET /api/inspecoes?modulo=DIARIO_OBRA&alvoId={id}
Campos: dataInspecao, classificacaoTempo, condicaoTrabalho
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import date, timedelta

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fvs_dashboard.core.data_manager import OBRAS, DATA_RAW
from fvs_dashboard.core.inmeta_client import InMetaClient
import os

# ── Histórico pré-InMeta (fixo) ───────────────────────────────────────────────
HISTORICAL = {
    "Cape Town Residence": {"ENSOLARADO": 129, "NUBLADO": 77, "CHUVOSO": 42},
    "Holmes Residence":    {"ENSOLARADO": 0,   "NUBLADO": 0,  "CHUVOSO": 0},
}

WEATHER_META = {
    "ENSOLARADO": {"icon": "☀️",  "label": "Ensolarado", "color": "#F6A623"},
    "NUBLADO":    {"icon": "⛅", "label": "Nublado",    "color": "#82A0C0"},
    "CHUVOSO":    {"icon": "🌧️", "label": "Chuvoso",    "color": "#4A7BB5"},
}
WEATHER_KEYS = list(WEATHER_META.keys())

MONTHS_PT    = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
                7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
MONTHS_SHORT = {k: v[:3] for k, v in MONTHS_PT.items()}

DIARIO_CACHE = DATA_RAW / "inmeta_diario_raw.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _secret(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


def _load_cache() -> dict:
    if not DIARIO_CACHE.exists():
        return {}
    try:
        return json.loads(DIARIO_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    DIARIO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DIARIO_CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── Normaliza classificacaoTempo ──────────────────────────────────────────────

def _normalize(val: str) -> str:
    v = str(val).upper().strip()
    if "ENSOL" in v or v == "BOM":
        return "ENSOLARADO"
    if "NUBLADO" in v or "PARCIAL" in v:
        return "NUBLADO"
    if "CHUV" in v:
        return "CHUVOSO"
    return v  # mantém o valor original se não reconhecido


# ── Fetch e cache ─────────────────────────────────────────────────────────────

def _do_refresh() -> tuple[bool, str]:
    try:
        client = InMetaClient(
            base_url=_secret("INMETA_BASE_URL", "https://api.inmeta.com.br"),
            email=_secret("INMETA_EMAIL"),
            senha=_secret("INMETA_SENHA"),
        )
        cache = {"collected_at": str(date.today())}
        total = 0
        for obra_name, cfg in OBRAS.items():
            rdos = client.fetch_diario_obra(cfg["inmeta_id"])
            cache[cfg["insp_key"]] = rdos
            total += len(rdos)
        _save_cache(cache)
        # Limpa cache de session_state
        for k in list(st.session_state.keys()):
            if k.startswith("diario_df_"):
                del st.session_state[k]
        return True, f"✅ {total} RDOs carregados."
    except Exception as e:
        return False, f"❌ {e}"


def _get_df(obra: str) -> pd.DataFrame:
    """Carrega RDOs da obra como DataFrame com colunas: data, condicao, condicao_trabalho."""
    key = f"diario_df_{obra}"
    if key in st.session_state:
        return st.session_state[key]

    cache = _load_cache()
    rdos  = cache.get(OBRAS[obra]["insp_key"], [])
    if not rdos:
        return pd.DataFrame(columns=["data", "condicao", "condicao_trabalho"])

    rows = []
    for r in rdos:
        data_str = r.get("dataInspecao", "") or ""
        cond     = _normalize(r.get("classificacaoTempo", "") or "")
        trab     = r.get("condicaoTrabalho", "") or ""
        rows.append({
            "data":             data_str[:10],
            "condicao":         cond,
            "condicao_trabalho": trab,
        })

    df = pd.DataFrame(rows)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = (df
          .dropna(subset=["data"])
          .sort_values("data")
          .drop_duplicates(subset=["data"], keep="last")   # 1 RDO por dia (mais recente)
          .reset_index(drop=True))
    st.session_state[key] = df
    return df


def _get_df_combined() -> pd.DataFrame:
    """
    Combina RDOs de todas as obras sem duplicidade de dias.
    Prioridade: Cape Town > Holmes.
    Se Cape Town nao tem RDO num dia, usa Holmes; caso contrario usa Cape Town.
    """
    key = "diario_df_combined"
    if key in st.session_state:
        return st.session_state[key]

    obra_names = list(OBRAS.keys())   # Cape Town = indice 0 (maior prioridade)
    frames = []
    for obra_name in obra_names:
        df_obra = _get_df(obra_name)
        if not df_obra.empty:
            df_obra = df_obra.copy()
            df_obra["_prio"] = obra_names.index(obra_name)
            frames.append(df_obra)

    if not frames:
        empty = pd.DataFrame(columns=["data", "condicao", "condicao_trabalho"])
        st.session_state[key] = empty
        return empty

    combined = pd.concat(frames, ignore_index=True)
    combined = (combined
                .sort_values(["data", "_prio"])          # menor _prio = maior prioridade
                .drop_duplicates(subset=["data"], keep="first")   # Cape Town ganha em conflito
                .drop(columns=["_prio"])
                .reset_index(drop=True))

    st.session_state[key] = combined
    return combined


# ── Agrega por mês ────────────────────────────────────────────────────────────

def _monthly(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["mes"] = df["data"].dt.to_period("M")
    grp = df.groupby(["mes", "condicao"]).size().unstack(fill_value=0).reset_index()
    for k in WEATHER_KEYS:
        if k not in grp.columns:
            grp[k] = 0
    grp["label"] = grp["mes"].apply(
        lambda p: f"{MONTHS_SHORT[p.month]}/{str(p.year)[-2:]}"
    )
    grp["total"] = grp[WEATHER_KEYS].sum(axis=1)
    return grp.sort_values("mes")


def _count_range(df: pd.DataFrame, d_start, d_end) -> dict[str, int]:
    """Conta dias por condicao num intervalo de datas [d_start, d_end] (inclusive)."""
    mask = (df["data"].dt.date >= d_start) & (df["data"].dt.date <= d_end)
    sub  = df[mask]
    return {k: int((sub["condicao"] == k).sum()) for k in WEATHER_KEYS}


# ── Cabeçalho de pizza (fora do gráfico) ────────────────────────────────────

def _pie_header(title: str, subtitle: str, total: int, accent: str) -> None:
    """Renderiza título, subtítulo e total de dias acima da pizza."""
    st.markdown(
        f"""<div style="
            background:linear-gradient(135deg,{accent}18 0%,{accent}08 100%);
            border-left:4px solid {accent};border-radius:8px;
            padding:10px 14px 8px;margin-bottom:2px;">
            <div style="font-size:13px;font-weight:800;color:{accent};
                letter-spacing:.3px;">{title}</div>
            <div style="font-size:11px;color:#555;margin:1px 0 6px;">{subtitle}</div>
            <div style="display:flex;align-items:baseline;gap:4px;">
                <span style="font-size:28px;font-weight:900;
                    color:#1A1A1A;line-height:1">{total}</span>
                <span style="font-size:12px;color:#777">dias</span>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


# ── Gráfico de pizza ─────────────────────────────────────────────────────────

def _make_pie(counts: dict[str, int]) -> go.Figure:
    """Pizza com rótulo + ícone + percentual dentro de cada fatia. Sem legenda separada."""
    labels = [f"{WEATHER_META[k]['icon']} {WEATHER_META[k]['label']}" for k in WEATHER_KEYS]
    values = [counts.get(k, 0) for k in WEATHER_KEYS]
    colors = [WEATHER_META[k]["color"] for k in WEATHER_KEYS]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.0,
        marker=dict(colors=colors, line=dict(color="#fff", width=2.5)),
        textinfo="label+percent",
        textposition="inside",
        insidetextorientation="horizontal",
        textfont=dict(size=13, color="#fff", family="Arial"),
        outsidetextfont=dict(size=11, color="#444"),   # fatias pequenas: texto fora
        hovertemplate="<b>%{label}</b><br>%{value} dias — %{percent}<extra></extra>",
        sort=False,
        pull=[0.025, 0.025, 0.025],
    ))
    fig.update_layout(
        showlegend=False,
        margin=dict(t=6, b=6, l=6, r=6),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=290,
    )
    return fig


_PLOTLY_CFG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["zoom2d","pan2d","select2d","lasso2d",
                                "zoomIn2d","zoomOut2d","autoScale2d","resetScale2d"],
    "toImageButtonOptions": {"format":"png","filename":"condicao_tempo",
                              "height":500,"width":600,"scale":2},
}


# ── Exportar PDF ──────────────────────────────────────────────────────────────

def _export_pdf(
    fig_total: go.Figure,
    fig_p1,
    fig_p2,
    fig_bar,
    obra: str,
    label_total_sub: str,
    label_p1: str,
    label_p2: str,
    total_total: int,
    total_p1: int,
    total_p2: int,
) -> bytes:
    """Gera PDF A4 com as 3 pizzas + evolução mensal usando reportlab + kaleido."""
    import io as _io
    import copy
    import plotly.io as pio
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors as rlc
    from reportlab.platypus import (
        SimpleDocTemplate, Image as RLImage, Paragraph,
        Spacer, Table, TableStyle, HRFlowable,
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    # ── render Plotly → PNG com fundo branco ──────────────────────────────────
    def _to_png(fig: go.Figure, w_px: int, h_px: int) -> bytes:
        f = copy.deepcopy(fig)
        f.update_layout(paper_bgcolor="white", plot_bgcolor="white")
        return pio.to_image(f, format="png", width=w_px, height=h_px, scale=2)

    # ── cores e estilos ───────────────────────────────────────────────────────
    C_RED   = rlc.HexColor("#C41230")
    C_DARK  = rlc.HexColor("#1A1A1A")
    C_GRAY  = rlc.HexColor("#666666")
    C_LGRAY = rlc.HexColor("#DDDDDD")
    C_BLUE  = rlc.HexColor("#82A0C0")
    C_YEL   = rlc.HexColor("#F6A623")

    def _ps(name, **kw):
        return ParagraphStyle(name, **kw)

    sty_title   = _ps("tt",  fontSize=17, fontName="Helvetica-Bold",  textColor=C_RED,   spaceAfter=2)
    sty_sub     = _ps("ts",  fontSize=9,  fontName="Helvetica",       textColor=C_GRAY,  spaceAfter=6)
    sty_section = _ps("tsc", fontSize=12, fontName="Helvetica-Bold",  textColor=C_DARK,  spaceBefore=6, spaceAfter=4)
    sty_footer  = _ps("tf",  fontSize=7,  fontName="Helvetica",       textColor=C_GRAY,  alignment=TA_CENTER, spaceBefore=3)

    def _sty_kpi(color):
        return _ps("kpi", fontSize=22, fontName="Helvetica-Bold", textColor=color, alignment=TA_CENTER)

    def _sty_cap(color):
        return _ps("cap", fontSize=10, fontName="Helvetica-Bold", textColor=color, alignment=TA_CENTER, spaceAfter=2)

    sty_micro = _ps("mc", fontSize=8, fontName="Helvetica", textColor=C_GRAY, alignment=TA_CENTER)

    # ── dimensões ─────────────────────────────────────────────────────────────
    W, H  = A4
    M     = 1.5 * cm
    use_w = W - 2 * M              # ~510 pt

    gap    = 0.5 * cm
    pie_pt = (use_w - 2 * gap) / 3   # ~160 pt per column
    pie_px = 420                      # render resolution
    bar_h_pt = use_w * 0.38
    bar_w_px = int(use_w * 3.2)
    bar_h_px = int(bar_h_pt * 3.2)

    # ── render em paralelo (ThreadPoolExecutor) ───────────────────────────────
    from concurrent.futures import ThreadPoolExecutor, as_completed
    jobs = {"total": (fig_total, pie_px, pie_px)}
    if fig_p1  is not None: jobs["p1"]  = (fig_p1,  pie_px, pie_px)
    if fig_p2  is not None: jobs["p2"]  = (fig_p2,  pie_px, pie_px)
    if fig_bar is not None: jobs["bar"] = (fig_bar,  bar_w_px, bar_h_px)

    rendered: dict = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        fs = {ex.submit(_to_png, *args): key for key, args in jobs.items()}
        for f in as_completed(fs):
            rendered[fs[f]] = f.result()

    # ── montagem da coluna de cada pizza ─────────────────────────────────────
    def _pie_col(key, accent, title, subtitle, dias):
        items = []
        if key in rendered:
            items.append(RLImage(_io.BytesIO(rendered[key]), width=pie_pt, height=pie_pt))
        else:
            items.append(Paragraph("sem dados", sty_micro))
        items.append(Spacer(1, 3))
        items.append(Paragraph(title,          _sty_cap(accent)))
        items.append(Paragraph(subtitle,       sty_micro))
        items.append(Spacer(1, 2))
        items.append(Paragraph(f"{dias} dias", _sty_kpi(accent)))
        return Table(
            [[it] for it in items],
            colWidths=[pie_pt],
            style=TableStyle([
                ("ALIGN",          (0, 0), (-1, -1), "CENTER"),
                ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",     (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING",  (0, 0), (-1, -1), 2),
            ]),
        )

    # ── documento ─────────────────────────────────────────────────────────────
    buf = _io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M,
        title="Condicao do Tempo - Diario de Obra",
        author="R21 Empreendimentos",
    )

    story = []

    # cabecalho (sem emoji — Helvetica nao suporta Unicode)
    story.append(Paragraph("Condicao do Tempo  —  Diario de Obra", sty_title))
    story.append(Paragraph(
        f"<b>{obra}</b> &nbsp;·&nbsp; Gerado em {date.today().strftime('%d/%m/%Y')}",
        sty_sub,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=C_RED, spaceAfter=10))

    # 3 pizzas
    story.append(Paragraph("Distribuicao por Condicao", sty_section))

    col_w = pie_pt + gap
    pie_row = Table(
        [[
            _pie_col("total", C_RED,  "Total Acumulado", label_total_sub, total_total),
            _pie_col("p1",    C_BLUE, "Periodo 1",       label_p1,        total_p1),
            _pie_col("p2",    C_YEL,  "Periodo 2",       label_p2,        total_p2),
        ]],
        colWidths=[col_w, col_w, col_w],
        style=TableStyle([
            ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]),
    )
    story.append(pie_row)
    story.append(Spacer(1, 0.4 * cm))

    # evolucao mensal
    if "bar" in rendered:
        story.append(HRFlowable(width="100%", thickness=1, color=C_LGRAY, spaceAfter=6))
        story.append(Paragraph("Evolucao Mensal", sty_section))
        story.append(RLImage(_io.BytesIO(rendered["bar"]), width=use_w, height=bar_h_pt))

    # rodape
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=C_LGRAY))
    story.append(Paragraph(
        "R21 Empreendimentos &nbsp;·&nbsp; FVS Dashboard &nbsp;·&nbsp; "
        "Fonte: InMeta Diario de Obra",
        sty_footer,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()

# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div style="background:linear-gradient(135deg,#8B0D22 0%,#C41230 100%);
    padding:18px 24px 14px;border-radius:10px;margin-bottom:20px;">
    <div style="font-size:22px;font-weight:800;color:#fff;">🌤️ Condição do Tempo</div>
    <div style="font-size:12px;color:rgba(255,255,255,0.75);margin-top:4px;">
        Diário de Obra — InMeta</div>
</div>""", unsafe_allow_html=True)

obra = st.session_state.get("obra", list(OBRAS.keys())[0])

# ── Barra de atualização ──────────────────────────────────────────────────────
c_info, c_btn = st.columns([3, 1])
cache_meta = _load_cache()
with c_info:
    if cache_meta.get("collected_at"):
        n_rdos = len(cache_meta.get(OBRAS[obra]["insp_key"], []))
        st.caption(f"📅 Atualizado em **{cache_meta['collected_at']}** — {n_rdos} RDOs de {obra}")
    else:
        st.caption("Sem dados. Clique em **Atualizar Diário**.")

with c_btn:
    if st.button("🔄 Atualizar Diário", use_container_width=True, type="primary"):
        with st.spinner("Buscando RDOs no InMeta..."):
            ok, msg = _do_refresh()
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

st.divider()

# ── Dados ────────────────────────────────────────────────────────────────────
df        = _get_df(obra)          # dados da obra selecionada (períodos 1 e 2)
df_comb   = _get_df_combined()     # todos os dias únicos, Cape Town > Holmes
hist      = HISTORICAL.get(obra, {})
df_months = _monthly(df)

# Totais acumulados (histórico pré-InMeta + InMeta combinado sem duplicidade de dias)
# Histórico existe apenas para Cape Town; Holmes = 0 → usamos o dict de Cape Town
hist_total    = HISTORICAL.get("Cape Town Residence", {})
counts_comb   = {k: int((df_comb["condicao"] == k).sum()) if not df_comb.empty else 0
                 for k in WEATHER_KEYS}
counts_total  = {k: hist_total.get(k, 0) + counts_comb[k] for k in WEATHER_KEYS}
# (mantém counts_inmeta por obra selecionada — usado na composição)
counts_inmeta = {k: int((df["condicao"] == k).sum()) if not df.empty else 0 for k in WEATHER_KEYS}

# ── Defaults de intervalo baseados nos dados disponíveis ─────────────────────
if not df.empty:
    d_min = df["data"].dt.date.min()
    d_max = df["data"].dt.date.max()
else:
    d_max = date.today()
    d_min = d_max - timedelta(days=365)

# Período 1 default: últimos 30 dias com dados
p1_end_def   = d_max
p1_start_def = max(d_min, d_max - timedelta(days=29))
# Período 2 default: 30 dias antes do período 1
p2_end_def   = p1_start_def - timedelta(days=1) if p1_start_def > d_min else d_min
p2_start_def = max(d_min, p2_end_def - timedelta(days=29))

# ── Seletores de intervalo ────────────────────────────────────────────────────
sc1, sc2 = st.columns(2)

with sc1:
    st.markdown("**📅 Período 1**")
    sel_p1 = st.date_input(
        "Período 1", label_visibility="collapsed",
        value=(p1_start_def, p1_end_def),
        min_value=d_min, max_value=d_max,
        format="DD/MM/YYYY", key="tp1",
    )
    if isinstance(sel_p1, (list, tuple)) and len(sel_p1) == 2:
        counts_p1 = _count_range(df, sel_p1[0], sel_p1[1])
        label_p1  = f"{sel_p1[0].strftime('%d/%m/%y')} – {sel_p1[1].strftime('%d/%m/%y')}"
    else:
        counts_p1 = label_p1 = None   # usuário ainda arrastando a seleção

with sc2:
    st.markdown("**📅 Período 2**")
    sel_p2 = st.date_input(
        "Período 2", label_visibility="collapsed",
        value=(p2_start_def, p2_end_def),
        min_value=d_min, max_value=d_max,
        format="DD/MM/YYYY", key="tp2",
    )
    if isinstance(sel_p2, (list, tuple)) and len(sel_p2) == 2:
        counts_p2 = _count_range(df, sel_p2[0], sel_p2[1])
        label_p2  = f"{sel_p2[0].strftime('%d/%m/%y')} – {sel_p2[1].strftime('%d/%m/%y')}"
    else:
        counts_p2 = label_p2 = None

st.markdown("")

# ── Preparar figuras (display + PDF) ─────────────────────────────────────────
h_tot     = sum(hist_total.values())
m_tot     = sum(counts_comb.values())
n_ct      = len(_get_df("Cape Town Residence"))
n_hm      = len(_get_df("Holmes Residence"))
_total_p1 = sum(counts_p1.values()) if counts_p1 is not None else 0
_total_p2 = sum(counts_p2.values()) if counts_p2 is not None else 0

_fig_total = _make_pie(counts_total)
_fig_p1    = _make_pie(counts_p1) if counts_p1 is not None else None
_fig_p2    = _make_pie(counts_p2) if counts_p2 is not None else None
_fig_bar   = None   # preenchido no bloco de evolução mensal

# ── 3 pizzas ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)

with c1:
    _pie_header("Total Acumulado", f"Pré-InMeta ({h_tot}d) + InMeta combinado ({len(df_comb)}d)",
                h_tot + m_tot, "#C41230")
    st.plotly_chart(_fig_total, use_container_width=True, config=_PLOTLY_CFG)
    st.markdown(
        f"""<div style="font-size:11px;color:#666;padding:4px 6px;
            background:rgba(0,0,0,0.03);border-radius:6px;line-height:1.7;">
            📚 Pré-InMeta <b>{h_tot}</b>d &nbsp;·&nbsp;
            📋 Cape Town <b>{n_ct}</b>d &nbsp;·&nbsp;
            📋 Holmes <b>{n_hm}</b>d &nbsp;·&nbsp;
            🔗 Combinado <b>{len(df_comb)}</b>d (sem duplic.)
        </div>""",
        unsafe_allow_html=True,
    )

with c2:
    if _fig_p1 is not None:
        _pie_header("Período 1", label_p1, _total_p1, "#82A0C0")
        st.plotly_chart(_fig_p1, use_container_width=True, config=_PLOTLY_CFG)
    else:
        st.info("Selecione um intervalo completo no Período 1.")

with c3:
    if _fig_p2 is not None:
        _pie_header("Período 2", label_p2, _total_p2, "#F6A623")
        st.plotly_chart(_fig_p2, use_container_width=True, config=_PLOTLY_CFG)
    else:
        st.info("Atualize o Diário para ver dados por período.")

# ── Evolução mensal ───────────────────────────────────────────────────────────
if not df_months.empty:
    st.divider()
    st.markdown("#### 📊 Evolução Mensal")

    _fig_bar = go.Figure()
    for k, color, name in [
        ("ENSOLARADO", "#F6A623", "☀️ Ensolarado"),
        ("NUBLADO",    "#82A0C0", "⛅ Nublado"),
        ("CHUVOSO",    "#4A7BB5", "🌧️ Chuvoso"),
    ]:
        _fig_bar.add_trace(go.Bar(
            name=name,
            x=df_months["label"],
            y=df_months[k],
            marker_color=color,
            text=df_months[k].where(df_months[k] > 0),
            textposition="inside",
        ))

    _fig_bar.update_layout(
        barmode="stack", height=300,
        margin=dict(t=20, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        xaxis=dict(tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(title="Dias", gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(_fig_bar, use_container_width=True, config={
        **_PLOTLY_CFG,
        "toImageButtonOptions": {**_PLOTLY_CFG["toImageButtonOptions"],
                                  "filename": "tempo_mensal", "width": 1000},
    })

    with st.expander("Ver tabela"):
        tbl = df_months[["label", "ENSOLARADO", "NUBLADO", "CHUVOSO", "total"]].copy()
        tbl.columns = ["Mês", "☀️ Ensolarado", "⛅ Nublado", "🌧️ Chuvoso", "Total"]
        st.dataframe(tbl, use_container_width=True, hide_index=True)

# ── Exportar PDF ──────────────────────────────────────────────────────────────
st.divider()
_lbl_total_sub = f"Pré-InMeta ({h_tot}d) + InMeta ({len(df_comb)}d)"

bc_gen, bc_dl = st.columns([1, 1])
with bc_gen:
    if st.button("📄 Gerar PDF", use_container_width=True, type="primary"):
        with st.spinner("Renderizando gráficos e montando PDF… (alguns segundos)"):
            try:
                _pdf_bytes = _export_pdf(
                    fig_total       = _fig_total,
                    fig_p1          = _fig_p1,
                    fig_p2          = _fig_p2,
                    fig_bar         = _fig_bar,
                    obra            = obra,
                    label_total_sub = _lbl_total_sub,
                    label_p1        = label_p1 or "—",
                    label_p2        = label_p2 or "—",
                    total_total     = h_tot + m_tot,
                    total_p1        = _total_p1,
                    total_p2        = _total_p2,
                )
                st.session_state["tempo_pdf"] = _pdf_bytes
                st.success("PDF pronto — clique em **Baixar PDF** ao lado.")
            except Exception as _exc:
                st.error(f"❌ Erro ao gerar PDF: {_exc}")

with bc_dl:
    if "tempo_pdf" in st.session_state:
        _fname = f"condicao_tempo_{obra.replace(' ', '_')}_{date.today()}.pdf"
        st.download_button(
            "⬇️ Baixar PDF",
            data        = st.session_state["tempo_pdf"],
            file_name   = _fname,
            mime        = "application/pdf",
            use_container_width = True,
        )
