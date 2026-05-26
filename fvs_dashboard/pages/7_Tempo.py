"""
Pagina 7 — Condicao do Tempo
============================
Le o relatorio do Diario de Obra (Excel/CSV exportado do InMeta)
e gera graficos de pizza interativos por periodo.
Historico pre-InMeta fixo: Cape Town Sol=129, Nub=77, Chu=42.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import date

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fvs_dashboard.core.data_manager import OBRAS, DATA_RAW

# ── Histórico pré-InMeta (fixo) ───────────────────────────────────────────────
HISTORICAL: dict[str, dict[str, int]] = {
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

WEATHER_CACHE = DATA_RAW / "weather_diario.json"

# ── Normalização ──────────────────────────────────────────────────────────────

def _normalize(val: str) -> str:
    v = str(val).upper().strip()
    if any(x in v for x in ["SOL", "ENSOL", "BOM", "CLARO"]):
        return "ENSOLARADO"
    if any(x in v for x in ["NUBLA", "PARCIAL", "ENCOBERTO"]):
        return "NUBLADO"
    if any(x in v for x in ["CHUV", "RAIN", "MOLHA"]):
        return "CHUVOSO"
    return "OUTRO"

# ── Cache JSON ────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    if not WEATHER_CACHE.exists():
        return {}
    try:
        return json.loads(WEATHER_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_cache(data: dict) -> None:
    WEATHER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    WEATHER_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _obra_key(obra: str) -> str:
    return OBRAS[obra]["insp_key"]

# ── Lê relatório do Diário de Obra ────────────────────────────────────────────

def _parse_diario(uploaded_file) -> pd.DataFrame:
    """
    Lê Excel ou CSV do relatório Diário de Obra.
    Detecta automaticamente colunas de data e condição do tempo.
    Retorna DataFrame com colunas: data (date), condicao (str normalizada).
    """
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, sep=None, engine="python", dtype=str)
    else:
        df = pd.read_excel(uploaded_file, dtype=str)

    df.columns = [str(c).strip() for c in df.columns]

    # ── Detecta coluna de condição ────────────────────────────────────────────
    clima_candidates = [c for c in df.columns if any(
        x in c.lower() for x in ["clima", "tempo", "condicao", "condicão",
                                  "weather", "situacao", "situação"]
    )]
    if not clima_candidates:
        raise ValueError(
            f"Coluna de condição do tempo não encontrada.\n"
            f"Colunas disponíveis: {list(df.columns)}"
        )
    col_clima = clima_candidates[0]

    # ── Detecta coluna de data ────────────────────────────────────────────────
    date_candidates = [c for c in df.columns if any(
        x in c.lower() for x in ["data", "date", "dia"]
    )]
    col_data = date_candidates[0] if date_candidates else None

    result = pd.DataFrame()
    result["condicao"] = df[col_clima].dropna().apply(_normalize)

    if col_data:
        result["data"] = pd.to_datetime(
            df[col_data], dayfirst=True, errors="coerce"
        )
    else:
        result["data"] = pd.NaT

    return result[["data", "condicao"]]

# ── Agrega por mês ────────────────────────────────────────────────────────────

def _aggregate_months(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """
    Retorna {"YYYY-MM": {"ENSOLARADO":n, "NUBLADO":n, "CHUVOSO":n}, ...}
    """
    result: dict[str, dict[str, int]] = {}
    for _, row in df.iterrows():
        cond = row["condicao"]
        if cond not in WEATHER_KEYS:
            continue
        if pd.notna(row["data"]):
            key = row["data"].strftime("%Y-%m")
        else:
            key = "sem-data"
        if key not in result:
            result[key] = {k: 0 for k in WEATHER_KEYS}
        result[key][cond] = result[key].get(cond, 0) + 1
    return result

# ── Soma todos os meses ───────────────────────────────────────────────────────

def _sum_months(months: dict) -> dict[str, int]:
    total = {k: 0 for k in WEATHER_KEYS}
    for m in months.values():
        for k in WEATHER_KEYS:
            total[k] += m.get(k, 0)
    return total

# ── Gráfico de pizza ─────────────────────────────────────────────────────────

def _make_pie(counts: dict[str, int], title: str) -> go.Figure:
    labels = [f"{WEATHER_META[k]['icon']} {WEATHER_META[k]['label']}" for k in WEATHER_KEYS]
    values = [counts.get(k, 0) for k in WEATHER_KEYS]
    colors = [WEATHER_META[k]["color"] for k in WEATHER_KEYS]
    total  = sum(values)

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.45,
        marker=dict(colors=colors, line=dict(color="#fff", width=2)),
        textinfo="label+percent",
        textfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>%{value} dias (%{percent})<extra></extra>",
        sort=False,
    ))
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>",
                   font=dict(size=14, color="#C41230", family="Arial Black"),
                   x=0.5, xanchor="center"),
        annotations=[dict(
            text=f"<b>{total}</b><br><span style='font-size:10px'>dias</span>",
            x=0.5, y=0.5, font=dict(size=20, color="#1A1A1A", family="Arial Black"),
            showarrow=False,
        )],
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.30, xanchor="center", x=0.5,
                    font=dict(size=11)),
        margin=dict(t=55, b=70, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
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
        Relatório do Diário de Obra + histórico pré-InMeta</div>
</div>""", unsafe_allow_html=True)

obra = st.session_state.get("obra", list(OBRAS.keys())[0])
cache = _load_cache()
obra_months: dict = cache.get(_obra_key(obra), {})

# ── Upload do relatório ───────────────────────────────────────────────────────
with st.expander("📂 Importar relatório do Diário de Obra", expanded=not bool(obra_months)):
    st.caption(
        "Exporte o Diário de Obra do InMeta (Excel ou CSV) e importe aqui. "
        "O arquivo precisa ter uma coluna com a data e outra com a condição do tempo."
    )
    uploaded = st.file_uploader(
        f"Relatório — {obra}",
        type=["xlsx", "xls", "csv"],
        key=f"upload_{obra}",
    )
    if uploaded:
        try:
            df_parsed = _parse_diario(uploaded)
            months_new = _aggregate_months(df_parsed)
            total_rows = sum(sum(m.values()) for m in months_new.values())

            st.success(
                f"✅ {total_rows} dias lidos em {len(months_new)} mês(es). "
                f"Confirme para salvar."
            )
            # Preview
            preview_rows = []
            for p in sorted(months_new.keys()):
                d = months_new[p]
                try:
                    yr, mo = int(p[:4]), int(p[5:])
                    label = f"{MONTHS_PT[mo]} {yr}"
                except Exception:
                    label = p
                preview_rows.append({
                    "Mês": label,
                    "☀️ Ensolarado": d.get("ENSOLARADO", 0),
                    "⛅ Nublado":    d.get("NUBLADO",    0),
                    "🌧️ Chuvoso":   d.get("CHUVOSO",    0),
                    "Total": sum(d.values()),
                })
            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

            col_save, col_replace = st.columns(2)
            with col_save:
                if st.button("💾 Adicionar aos dados existentes", use_container_width=True,
                             type="primary"):
                    cache.setdefault(_obra_key(obra), {}).update(months_new)
                    _save_cache(cache)
                    st.success("Dados adicionados!")
                    st.rerun()
            with col_replace:
                if st.button("🔄 Substituir todos os dados desta obra", use_container_width=True):
                    cache[_obra_key(obra)] = months_new
                    _save_cache(cache)
                    st.success("Dados substituídos!")
                    st.rerun()

        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")
            st.info("Verifique se o arquivo tem colunas de **data** e **condição do tempo**.")

st.divider()

# ── Carrega totais ────────────────────────────────────────────────────────────
hist          = HISTORICAL.get(obra, {})
counts_manual = _sum_months(obra_months)
counts_total  = {k: hist.get(k, 0) + counts_manual.get(k, 0) for k in WEATHER_KEYS}

periods       = sorted(p for p in obra_months if p != "sem-data")
period_labels = []
for p in periods:
    try:
        period_labels.append(f"{MONTHS_SHORT[int(p[5:7])]}/{p[2:4]}")
    except Exception:
        period_labels.append(p)

# ── Seletores de período ──────────────────────────────────────────────────────
sc1, sc2 = st.columns(2)
with sc1:
    if period_labels:
        sel_p1   = st.selectbox("Período 1", period_labels,
                                index=max(0, len(periods)-1), key="tp1")
        p1_key   = periods[period_labels.index(sel_p1)]
        counts_p1 = obra_months.get(p1_key, {k: 0 for k in WEATHER_KEYS})
        try:
            label_p1 = f"{MONTHS_PT[int(p1_key[5:7])]} {p1_key[:4]}"
        except Exception:
            label_p1 = p1_key
    else:
        st.selectbox("Período 1", ["(sem dados)"], disabled=True, key="tp1")
        counts_p1 = label_p1 = None

with sc2:
    if period_labels:
        sel_p2   = st.selectbox("Período 2", period_labels,
                                index=max(0, len(periods)-2), key="tp2")
        p2_key   = periods[period_labels.index(sel_p2)]
        counts_p2 = obra_months.get(p2_key, {k: 0 for k in WEATHER_KEYS})
        try:
            label_p2 = f"{MONTHS_PT[int(p2_key[5:7])]} {p2_key[:4]}"
        except Exception:
            label_p2 = p2_key
    else:
        st.selectbox("Período 2", ["(sem dados)"], disabled=True, key="tp2")
        counts_p2 = label_p2 = None

st.markdown("")

# ── 3 pizzas ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)

with c1:
    st.plotly_chart(_make_pie(counts_total, "Total Acumulado"),
                    use_container_width=True, config=_PLOTLY_CFG)
    h_tot = sum(hist.values())
    m_tot = sum(counts_manual.values())
    st.markdown(
        f"""<div style="background:rgba(196,18,48,0.06);border-left:3px solid #C41230;
            border-radius:6px;padding:10px 14px;font-size:12px;">
            <div style="font-weight:700;color:#C41230;margin-bottom:6px;">Composição</div>
            <div>📚 Pré-InMeta: <b>{h_tot}</b> dias</div>
            <div>📋 Diário InMeta: <b>{m_tot}</b> dias ({len(obra_months)} meses)</div>
            <div style="margin-top:6px;border-top:1px solid rgba(196,18,48,0.2);padding-top:6px;">
                <b>Total: {h_tot+m_tot}</b> dias</div></div>""",
        unsafe_allow_html=True,
    )

def _pie_col(counts, label, border):
    if counts is None:
        st.markdown(
            """<div style="display:flex;align-items:center;justify-content:center;
                height:340px;background:rgba(0,0,0,0.04);border-radius:10px;
                border:1px dashed #ccc;flex-direction:column;gap:8px;">
                <div style="font-size:36px;">📂</div>
                <div style="font-size:13px;color:#888;text-align:center;">
                    Importe o relatório do<br>Diário de Obra acima.</div>
            </div>""", unsafe_allow_html=True)
        return
    st.plotly_chart(_make_pie(counts, label),
                    use_container_width=True, config=_PLOTLY_CFG)
    total = sum(counts.get(k, 0) for k in WEATHER_KEYS)
    lines = "".join(
        f"<div>{WEATHER_META[k]['icon']} {WEATHER_META[k]['label']}: "
        f"<b>{counts.get(k,0)}</b> "
        f"({'—' if total==0 else f'{counts.get(k,0)/total*100:.0f}%'})</div>"
        for k in WEATHER_KEYS
    )
    st.markdown(
        f"""<div style="background:rgba(0,0,0,0.04);border-left:3px solid {border};
            border-radius:6px;padding:10px 14px;font-size:12px;">
            <div style="font-weight:700;color:{border};margin-bottom:6px;">{label}</div>
            {lines}
            <div style="margin-top:6px;border-top:1px solid rgba(0,0,0,0.1);padding-top:6px;">
                <b>Total: {total}</b> dias</div></div>""",
        unsafe_allow_html=True,
    )

with c2:
    _pie_col(counts_p1, label_p1 or "Período 1", "#82A0C0")
with c3:
    _pie_col(counts_p2, label_p2 or "Período 2", "#F6A623")

# ── Evolução mensal ───────────────────────────────────────────────────────────
if obra_months:
    st.divider()
    st.markdown("#### 📊 Evolução Mensal")

    rows_bar = []
    for p in periods:
        d = obra_months[p]
        try:
            lbl = f"{MONTHS_SHORT[int(p[5:7])]}/{p[2:4]}"
        except Exception:
            lbl = p
        rows_bar.append({"Mês": lbl,
                         "Ensolarado": d.get("ENSOLARADO", 0),
                         "Nublado":    d.get("NUBLADO",    0),
                         "Chuvoso":    d.get("CHUVOSO",    0)})

    df_bar = pd.DataFrame(rows_bar)
    fig_bar = go.Figure()
    for col, color, name in [("Ensolarado","#F6A623","☀️ Ensolarado"),
                               ("Nublado",   "#82A0C0","⛅ Nublado"),
                               ("Chuvoso",   "#4A7BB5","🌧️ Chuvoso")]:
        fig_bar.add_trace(go.Bar(
            name=name, x=df_bar["Mês"], y=df_bar[col],
            marker_color=color, text=df_bar[col], textposition="inside",
        ))
    fig_bar.update_layout(
        barmode="stack", height=300,
        margin=dict(t=20, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(title="Dias", gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig_bar, use_container_width=True, config={
        **_PLOTLY_CFG,
        "toImageButtonOptions": {**_PLOTLY_CFG["toImageButtonOptions"],
                                  "filename":"tempo_mensal","width":1000},
    })

    with st.expander("Ver tabela"):
        df_bar["Total"] = df_bar["Ensolarado"] + df_bar["Nublado"] + df_bar["Chuvoso"]
        st.dataframe(df_bar, use_container_width=True, hide_index=True)

    # Opção de limpar dados
    if st.button("🗑️ Limpar dados importados desta obra", type="secondary"):
        cache.pop(_obra_key(obra), None)
        _save_cache(cache)
        st.rerun()

st.markdown(
    """<div style="margin-top:20px;padding:10px 14px;background:rgba(0,0,0,0.03);
        border-radius:6px;font-size:11px;color:#888;">
        ℹ️ Exporte o <b>Diário de Obra</b> do InMeta em Excel ou CSV e importe aqui.
        Clique no ícone 📷 em qualquer gráfico para salvar como imagem.</div>""",
    unsafe_allow_html=True,
)
