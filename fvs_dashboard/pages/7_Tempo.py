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
    """Pizza limpa: sem título interno, sem anotação central, legenda lateral."""
    labels = [f"{WEATHER_META[k]['icon']} {WEATHER_META[k]['label']}" for k in WEATHER_KEYS]
    values = [counts.get(k, 0) for k in WEATHER_KEYS]
    colors = [WEATHER_META[k]["color"] for k in WEATHER_KEYS]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.0,                                   # pizza sólida — sem buraco
        marker=dict(colors=colors, line=dict(color="#fff", width=2.5)),
        textinfo="percent",
        textfont=dict(size=13, color="#fff"),
        insidetextorientation="radial",
        hovertemplate="<b>%{label}</b><br>%{value} dias — %{percent}<extra></extra>",
        sort=False,
        pull=[0.02, 0.02, 0.02],                   # leve separação entre fatias
    ))
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle", y=0.5,
            xanchor="left",   x=1.02,
            font=dict(size=12),
            bgcolor="rgba(0,0,0,0)",
            itemwidth=30,
        ),
        margin=dict(t=8, b=8, l=8, r=120),        # margem direita para a legenda
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=260,
    )
    return fig


_PLOTLY_CFG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["zoom2d","pan2d","select2d","lasso2d",
                                "zoomIn2d","zoomOut2d","autoScale2d","resetScale2d"],
    "toImageButtonOptions": {"format":"png","filename":"condicao_tempo",
                              "height":500,"width":600,"scale":2},
}

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

# ── 3 pizzas ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)

with c1:
    h_tot = sum(hist_total.values())
    m_tot = sum(counts_comb.values())
    n_ct  = len(_get_df("Cape Town Residence"))
    n_hm  = len(_get_df("Holmes Residence"))
    _pie_header("Total Acumulado", f"Pré-InMeta ({h_tot}d) + InMeta combinado ({len(df_comb)}d)",
                h_tot + m_tot, "#C41230")
    st.plotly_chart(_make_pie(counts_total),
                    use_container_width=True, config=_PLOTLY_CFG)
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
    if counts_p1 is not None:
        total_p1 = sum(counts_p1.values())
        _pie_header("Período 1", label_p1, total_p1, "#82A0C0")
        st.plotly_chart(_make_pie(counts_p1),
                        use_container_width=True, config=_PLOTLY_CFG)
    else:
        st.info("Selecione um intervalo completo no Período 1.")

with c3:
    if counts_p2 is not None:
        total_p2 = sum(counts_p2.values())
        _pie_header("Período 2", label_p2, total_p2, "#F6A623")
        st.plotly_chart(_make_pie(counts_p2),
                        use_container_width=True, config=_PLOTLY_CFG)
    else:
        st.info("Atualize o Diário para ver dados por período.")

# ── Evolução mensal ───────────────────────────────────────────────────────────
if not df_months.empty:
    st.divider()
    st.markdown("#### 📊 Evolução Mensal")

    fig_bar = go.Figure()
    for k, color, name in [
        ("ENSOLARADO", "#F6A623", "☀️ Ensolarado"),
        ("NUBLADO",    "#82A0C0", "⛅ Nublado"),
        ("CHUVOSO",    "#4A7BB5", "🌧️ Chuvoso"),
    ]:
        fig_bar.add_trace(go.Bar(
            name=name,
            x=df_months["label"],
            y=df_months[k],
            marker_color=color,
            text=df_months[k].where(df_months[k] > 0),
            textposition="inside",
        ))

    fig_bar.update_layout(
        barmode="stack", height=300,
        margin=dict(t=20, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        xaxis=dict(tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(title="Dias", gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig_bar, use_container_width=True, config={
        **_PLOTLY_CFG,
        "toImageButtonOptions": {**_PLOTLY_CFG["toImageButtonOptions"],
                                  "filename": "tempo_mensal", "width": 1000},
    })

    with st.expander("Ver tabela"):
        tbl = df_months[["label", "ENSOLARADO", "NUBLADO", "CHUVOSO", "total"]].copy()
        tbl.columns = ["Mês", "☀️ Ensolarado", "⛅ Nublado", "🌧️ Chuvoso", "Total"]
        st.dataframe(tbl, use_container_width=True, hide_index=True)
