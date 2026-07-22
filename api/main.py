"""
API FVS — camada HTTP sobre a logica Python existente.
=======================================================
Nao reimplementa regra de negocio: apenas expoe DataManager / audit_engine
para o frontend web (React).

Executar (a partir de prevision_agent/):
    uvicorn api.main:app --reload --port 8001

Endpoints:
    GET /api/health
    GET /api/obras
    GET /api/status
    GET /api/overview?obra=...      → tudo que a tela Visao Geral precisa
    GET /api/backlog?obra=...       → linhas de FVS (tabela)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import datetime
import os
import unicodedata
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from fvs_dashboard.core.data_manager import DataManager, OBRAS
from fvs_dashboard.core.audit_engine import (
    build_monthly_from_inspections, build_obra_comparison, compute_audit_kpis,
    compute_sla, load_raw_inspections, period_dates,
)
from api.report import build_backlog_report
from api.report_tempo import build_tempo_report
from api.auth import usuario_atual, descrever_modo

app = FastAPI(title="FVS API — R21", version="1.0.0")

# Origens liberadas. Em producao, defina FVS_ORIGENS com o dominio do frontend
# (separado por virgula) — sem isso o navegador bloqueia as chamadas.
_ORIGENS = [
    o.strip()
    for o in (
        os.getenv("FVS_ORIGENS") or "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGENS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)

_dm = DataManager()

print(f"[api] Autenticacao: {descrever_modo()}", flush=True)


def _check_obra(obra: str) -> str:
    if obra not in OBRAS:
        raise HTTPException(404, f"Obra desconhecida: {obra}")
    return obra


def _clean(value):
    """
    Guarda defensiva: descarta surrogates soltos antes de serializar em JSON.

    O cache atual esta integro (UTF-8 valido), mas um surrogate solto vindo de
    uma coleta futura quebraria a resposta no navegador. Para strings validas
    esta funcao e um no-op.
    """
    if isinstance(value, str):
        return value.encode("utf-8", "ignore").decode("utf-8", "ignore")
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


# ── Meta ──────────────────────────────────────────────────────────────────────

def _checar_pdf() -> bool:
    """
    O kaleido embute um chromium para transformar graficos Plotly em imagem.
    Se faltar biblioteca de sistema no host, so a exportacao em PDF quebra — e
    em runtime, no meio de uma reuniao. Aqui a capacidade e verificada uma vez
    na subida, para aparecer no health check em vez de virar surpresa.
    """
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
        fig = go.Figure(go.Bar(x=[1], y=[1]))
        pio.to_image(fig, format="png", width=80, height=60)
        return True
    except Exception as exc:      # noqa: BLE001 — diagnostico, nao pode derrubar
        print(f"[api] AVISO: geracao de PDF indisponivel ({exc})", flush=True)
        return False


_PDF_OK = _checar_pdf()
print(f"[api] Exportacao em PDF: {'ok' if _PDF_OK else 'INDISPONIVEL'}", flush=True)


@app.get("/api/health")
def health():
    """
    Aberto de proposito: usado pelo monitoramento do host.

    Inclui o commit implantado — sem isso nao da para saber, de fora, se o
    deploy acompanhou o frontend. Um front novo com API velha aparece para o
    usuario como erro de dados, nao como versao defasada.
    """
    return {
        "ok": True,
        "pdf": _PDF_OK,
        # Render/Vercel expoem o commit; local fica "dev"
        "commit": (os.getenv("RENDER_GIT_COMMIT")
                   or os.getenv("VERCEL_GIT_COMMIT_SHA") or "dev")[:7],
        "periodos": sorted(PERIODOS),
    }


@app.get("/api/obras")
def obras():
    return {"obras": list(OBRAS.keys())}


@app.get("/api/status")
def status(obra: str = Query(default=None),
    _usuario: str = Depends(usuario_atual),
):
    o = obra or list(OBRAS.keys())[0]
    _check_obra(o)
    ages = _dm.cache_age(o)
    return {
        "obra": o,
        "prevision": ages["prevision"],
        "inmeta": ages["inmeta"],
        "inmeta_horas": _dm.inmeta_age_hours(),
        "snapshots": _dm.snapshot_info(o),
    }


# ── Serie de evolucao ─────────────────────────────────────────────────────────

# Dias distintos de snapshot necessarios para o historico real substituir o proxy.
LIMIAR_SNAPSHOTS = 5


def _serie_evolucao(obra: str) -> tuple[list[dict], str, int]:
    """
    Devolve (serie, fonte, dias_de_snapshot).

    fonte="snapshots": historico REAL e congelado — cada ponto e o estado do
        backlog naquele dia. So fica disponivel apos LIMIAR_SNAPSHOTS dias.

    fonte="inspecoes": aproximacao. Agrupa as inspecoes ATUAIS pelo mes da
        dataInspecao. Nao e historico congelado: se uma FVS de 2025 for
        finalizada hoje, a barra de 2025 muda retroativamente. E o unico
        recurso possivel enquanto nao ha snapshots suficientes, porque a API do
        InMeta nao expoe data de finalizacao nem log de mudanca de status.
    """
    dias = 0
    try:
        hist = _dm.load_history(obra)
        if not hist.empty and "date_snapshot" in hist.columns:
            dias = int(hist["date_snapshot"].nunique())
            if dias >= LIMIAR_SNAPSHOTS:
                serie = []
                for data, grupo in hist.groupby("date_snapshot", sort=True):
                    st = grupo["status"]
                    serie.append({
                        "data":         data.isoformat() if hasattr(data, "isoformat") else str(data),
                        "finalizada":   int((st == "FINALIZADA").sum()),
                        "em_andamento": int((st == "EM_ANDAMENTO").sum()),
                        "nao_iniciada": int((st == "NAO_INICIADA").sum()),
                        "total":        int(len(grupo)),
                    })
                return serie, "snapshots", dias
    except Exception:
        dias = 0

    serie = []
    mi = build_monthly_from_inspections(obra)
    if not mi.empty:
        for _, r in mi.sort_values("date_month").iterrows():
            serie.append({
                "data":       r["date_month"].isoformat(),
                "finalizada": int(r["finalizada"]),
                "nc_total":   int(r["nc_total"]),
                "total":      int(r["total_insp"]),
            })
    return serie, "inspecoes", dias


def _idade_caches(obra: str) -> dict[str, float | None]:
    """Idade dos caches em horas — base para o alerta de dado desatualizado."""
    agora = datetime.datetime.now()
    idades: dict[str, float | None] = {}
    for chave, quando in _dm.cache_mtime(obra).items():
        idades[chave] = round((agora - quando).total_seconds() / 3600, 1) if quando else None
    return idades


# ── Visao Geral ───────────────────────────────────────────────────────────────

@app.get("/api/overview")
def overview(obra: str = Query(...),
    _usuario: str = Depends(usuario_atual),
):
    _check_obra(obra)
    try:
        kpis = _dm.get_kpis(obra)
        rows = _dm.get_rows(obra)
        top  = _dm.get_top_modelos(obra, n=6)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Cache indisponivel: {exc}")

    fvs_com_nc = sum(1 for r in rows if r["nc"] > 0)

    # ── Top modelos ───────────────────────────────────────────────────────────
    top_modelos = []
    if not top.empty:
        for _, r in top.iterrows():
            pend = int(r["Em_Andamento"]) + int(r["Nao_Iniciada"])
            top_modelos.append({
                "modelo":       str(r["Modelo FVS"]),
                "total":        int(r["Total"]),
                "finalizada":   int(r["Finalizada"]),
                "em_andamento": int(r["Em_Andamento"]),
                "nao_iniciada": int(r["Nao_Iniciada"]),
                "pendentes":    pend,
                "nc":           int(r["NC"]),
            })
        top_modelos.sort(key=lambda m: m["pendentes"], reverse=True)

    # ── Evolucao ─────────────────────────────────────────────────────────────
    evolucao, fonte, dias_snap = _serie_evolucao(obra)

    # ── Aging do backlog (snapshot mais recente) ─────────────────────────────
    aging: list[dict] = []
    try:
        snap = _dm.load_latest_snapshot(obra)
        if not snap.empty and "faixa_aging" in snap.columns:
            pend = snap[snap["status"] != "FINALIZADA"]
            for faixa in ["0-3d", "4-7d", "8-14d", ">14d"]:
                aging.append({
                    "faixa": faixa,
                    "qtd":   int((pend["faixa_aging"] == faixa).sum()),
                })
    except Exception:
        aging = []

    # ── Universo completo da obra (todas as inspecoes do InMeta) ─────────────
    # Contexto diferente dos KPIs: aqui entra TODA a obra, inclusive pacotes ja
    # encerrados (conferencia final 100%). Serve para explicar por que o
    # backlog mostra poucas FVS perto do total do painel do InMeta.
    insp_obra = load_raw_inspections(obra)
    obra_total = {
        "realizadas":   len(insp_obra),
        "concluidas":   sum(1 for i in insp_obra if i.get("status") == "FINALIZADA"),
        "em_andamento": sum(1 for i in insp_obra if i.get("status") == "EM_ANDAMENTO"),
        "nc_abertas":   sum(int(i.get("qtdNaoConformidade") or 0) for i in insp_obra),
    }
    # Nao expomos contagem de modelos: aqui so daria os modelos *usados* em
    # inspecoes (67), enquanto o painel do InMeta mostra os *cadastrados* na
    # obra (115) — numeros diferentes que gerariam a mesma confusao que este
    # bloco existe para eliminar.

    ages = _dm.cache_age(obra)

    return {
        "obra": obra,
        "obra_total": obra_total,
        "kpis": {
            "pacotes_liberados": kpis["total_lib"],
            "total_fvs":         kpis["total_fvs"],
            "finalizada":        kpis["finalizada"],
            "em_andamento":      kpis["em_andamento"],
            "nao_iniciada":      kpis["nao_iniciada"],
            "pct_finalizada":    kpis["pct_finalizada"],
            "pct_em_andamento":  kpis["pct_em_andamento"],
            "pct_nao_iniciada":  kpis["pct_nao_iniciada"],
            "nc_total":          kpis["nc_total"],
            "fvs_com_nc":        fvs_com_nc,
        },
        "top_modelos": top_modelos,
        "evolucao":    evolucao,
        "evolucao_meta": {
            "fonte":        fonte,          # "snapshots" (real) | "inspecoes" (proxy)
            "dias_snap":    dias_snap,      # dias de historico ja acumulados
            "dias_faltam":  max(0, LIMIAR_SNAPSHOTS - dias_snap) if fonte == "inspecoes" else 0,
        },
        "aging":       aging,
        # Idade numerica dos caches — permite a tela alertar quando o dado
        # envelhece. O texto sozinho ("ha 69d") ficava num canto da barra
        # lateral e passou 69 dias sem ninguem notar.
        "cache_horas": _idade_caches(obra),
        "cache": {"prevision": ages["prevision"], "inmeta": ages["inmeta"]},
    }


# ── Backlog ───────────────────────────────────────────────────────────────────

STATUS_VALIDOS = {"FINALIZADA", "EM_ANDAMENTO", "NAO_INICIADA"}

_ROTULO_STATUS = {
    "FINALIZADA": "Finalizadas",
    "EM_ANDAMENTO": "Em andamento",
    "NAO_INICIADA": "Nao iniciadas",
}


def _norm(texto: str) -> str:
    """minusculas sem acento — busca tolerante a acentuacao."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def filtrar_rows(
    rows: list[dict],
    status: list[str] | None = None,
    modelo: str = "",
    pavimento: str = "",
    busca: str = "",
) -> list[dict]:
    """
    Filtro unico do backlog — usado pela listagem e pela exportacao, garantindo
    que o relatorio contenha exatamente o que esta na tela.
    Lista de status vazia = todos os status.
    """
    alvo_status = {s for s in (status or []) if s in STATUS_VALIDOS}
    termo = _norm(busca.strip())

    resultado = []
    for r in rows:
        if alvo_status and r.get("status") not in alvo_status:
            continue
        if modelo and r.get("modelo") != modelo:
            continue
        if pavimento and r.get("floor") != pavimento:
            continue
        if termo:
            campos = f"{r.get('modelo','')} {r.get('local','')} {r.get('floor','')} {r.get('wbs','')}"
            if termo not in _norm(campos):
                continue
        resultado.append(r)
    return resultado


@app.get("/api/backlog")
def backlog(obra: str = Query(...), limit: int = Query(default=5000, le=20000),
    _usuario: str = Depends(usuario_atual),
):
    """
    Todas as FVS de pacotes liberados + facetas para os filtros.
    A filtragem em si acontece no cliente (volume pequeno, resposta instantanea).
    """
    _check_obra(obra)
    try:
        rows = _dm.get_rows(obra)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Cache indisponivel: {exc}")

    rows = [_clean(r) for r in rows[:limit]]

    modelos    = sorted({r["modelo"] for r in rows if r.get("modelo")})
    pavimentos = sorted({r["floor"] for r in rows if r.get("floor")})
    contagem   = {
        "FINALIZADA":   sum(1 for r in rows if r["status"] == "FINALIZADA"),
        "EM_ANDAMENTO": sum(1 for r in rows if r["status"] == "EM_ANDAMENTO"),
        "NAO_INICIADA": sum(1 for r in rows if r["status"] == "NAO_INICIADA"),
    }

    return {
        "obra": obra,
        "total": len(rows),
        "rows": rows,
        "facetas": {"modelos": modelos, "pavimentos": pavimentos},
        "contagem": contagem,
    }


# ── Auditoria Gerencial ───────────────────────────────────────────────────────

PERIODOS = {"Dia", "Semana", "Mes", "Trimestre", "Semestre", "Anual", "Tudo", "Personalizado"}

# Granularidade da serie por periodo. Filtrar 14 dias e plotar por mes daria
# um unico ponto — a escala do grafico acompanha o recorte.
GRANULARIDADE = {
    "Dia":       "dia",
    "Semana":    "semana",
    "Mes":       "dia",
    "Trimestre": "semana",
}       # demais periodos: mensal


def _intervalo_periodo(periodo: str, d_ini, d_fim):
    """Dia e Semana sao proprios da tela nova; o resto delega ao audit_engine."""
    hoje = datetime.date.today()
    if periodo == "Dia":
        return hoje - datetime.timedelta(days=13), hoje      # 14 dias
    if periodo == "Semana":
        return hoje - datetime.timedelta(weeks=11), hoje     # 12 semanas
    return period_dates(periodo, d_ini, d_fim)


def _serie_inspecoes(obra: str, inicio, fim, granularidade: str) -> list[dict]:
    """
    Agrupa as inspecoes do InMeta por dia, semana ou mes.

    Mesma ressalva do grafico da Visao Geral: e o status ATUAL agrupado pela
    data da inspecao, nao um historico congelado.
    """
    registros: dict[datetime.date, dict[str, int]] = {}

    for ins in load_raw_inspections(obra or None):
        bruto = (ins.get("dataInspecao") or "")[:10]
        if not bruto:
            continue
        try:
            dia = datetime.date.fromisoformat(bruto)
        except ValueError:
            continue
        if not (inicio <= dia <= fim):
            continue

        if granularidade == "dia":
            chave = dia
        elif granularidade == "semana":
            chave = dia - datetime.timedelta(days=dia.weekday())   # segunda
        else:
            chave = dia.replace(day=1)

        alvo = registros.setdefault(chave, {
            "finalizada": 0, "em_andamento": 0, "nc_total": 0, "total": 0,
        })
        status = ins.get("status", "")
        if status == "FINALIZADA":
            alvo["finalizada"] += 1
        elif status == "EM_ANDAMENTO":
            alvo["em_andamento"] += 1
        alvo["nc_total"] += int(ins.get("qtdNaoConformidade") or 0)
        alvo["total"] += 1

    return [{"data": d.isoformat(), **v} for d, v in sorted(registros.items())]


def _dados_auditoria(obra: str, periodo: str, de: str, ate: str):
    """
    Nucleo da auditoria — usado pela tela E pelas exportacoes.
    Centralizado para o PDF/Excel nunca divergirem do que esta na tela.
    Retorna (mi_periodo, mi_todas, snap, hist, kpis, inicio, fim, filtro_obra).
    """
    if obra and obra not in OBRAS:
        raise HTTPException(404, f"Obra desconhecida: {obra}")
    if periodo not in PERIODOS:
        raise HTTPException(400, f"Periodo invalido: {periodo}")

    d_ini = d_fim = None
    if periodo == "Personalizado":
        try:
            d_ini = datetime.date.fromisoformat(de) if de else None
            d_fim = datetime.date.fromisoformat(ate) if ate else None
        except ValueError:
            raise HTTPException(400, "Datas devem estar no formato AAAA-MM-DD.")

    inicio, fim = _intervalo_periodo(periodo, d_ini, d_fim)
    filtro_obra = obra or None

    mi_todas = build_monthly_from_inspections()
    mi = mi_todas.copy()
    if not mi.empty:
        if filtro_obra:
            mi = mi[mi["obra"] == filtro_obra]
        mi = mi[(mi["date_month"] >= inicio) & (mi["date_month"] <= fim)]

    # Snapshot mais recente (estado atual) + historico para SLA/aging
    alvos = [obra] if obra else list(OBRAS.keys())
    hist_partes, snap_partes = [], []
    for o in alvos:
        try:
            h = _dm.load_history(o)
            if not h.empty:
                hist_partes.append(h)
            s = _dm.load_latest_snapshot(o)
            if not s.empty:
                snap_partes.append(s)
        except Exception:
            pass

    import pandas as pd
    hist = pd.concat(hist_partes, ignore_index=True) if hist_partes else pd.DataFrame()
    snap = pd.concat(snap_partes, ignore_index=True) if snap_partes else pd.DataFrame()

    kpis = compute_audit_kpis(mi_todas, snap, inicio, fim, filtro_obra)
    return mi, mi_todas, snap, hist, kpis, inicio, fim, filtro_obra


@app.get("/api/auditoria")
def auditoria(
    obra: str = Query(default=""),          # "" = todas as obras
    periodo: str = Query(default="Tudo"),
    de: str = Query(default=""),            # ISO, usado com periodo=Personalizado
    ate: str = Query(default=""),
    _usuario: str = Depends(usuario_atual),
):
    """Indicadores gerenciais historicos (mesma base das exportacoes)."""
    mi, mi_todas, snap, hist, kpis, inicio, fim, filtro_obra = _dados_auditoria(
        obra, periodo, de, ate,
    )
    sla = compute_sla(hist) if not hist.empty else {}

    # ── Serie na granularidade do periodo (dia / semana / mes) ───────────────
    granularidade = GRANULARIDADE.get(periodo, "mes")
    serie = _serie_inspecoes(obra, inicio, fim, granularidade)

    # KPIs do periodo derivados da MESMA serie do grafico.
    #
    # compute_audit_kpis() filtra a agregacao mensal por date_month dentro do
    # intervalo. Para recortes menores que um mes isso zera tudo: no filtro
    # "Dia" (09/07 a 22/07) o balde do mes e 01/07, anterior ao inicio, e some.
    # Calculando daqui, numero do card e curva do grafico nunca divergem.
    total_periodo = {
        "total_insp":   sum(p["total"] for p in serie),
        "finalizada":   sum(p["finalizada"] for p in serie),
        "em_andamento": sum(p["em_andamento"] for p in serie),
        "nc_total":     sum(p["nc_total"] for p in serie),
    }
    total_periodo["pct_finalizada"] = round(
        100 * total_periodo["finalizada"] / total_periodo["total_insp"], 1
    ) if total_periodo["total_insp"] else 0.0

    # ── Comparativo entre obras ──────────────────────────────────────────────
    comparativo = []
    comp = build_obra_comparison(mi_todas)
    if not comp.empty:
        comp = comp[(comp["date_month"] >= inicio) & (comp["date_month"] <= fim)]
        for _, r in comp.iterrows():
            comparativo.append({
                "mes":       r["date_month"].isoformat(),
                "cape_town": int(r.get("fin_ct", 0)),
                "holmes":    int(r.get("fin_hm", 0)),
            })

    # ── Aging + alertas criticos (estado atual) ──────────────────────────────
    aging, criticas = [], []
    if not snap.empty:
        pend = snap[snap["status"] != "FINALIZADA"]
        if "faixa_aging" in snap.columns:
            for faixa in ["0-3d", "4-7d", "8-14d", ">14d"]:
                aging.append({"faixa": faixa, "qtd": int((pend["faixa_aging"] == faixa).sum())})

        if "dias_pendente" in snap.columns:
            crit = snap[(snap["status"] == "NAO_INICIADA") & (snap["dias_pendente"] > 7)]
            crit = crit.sort_values("dias_pendente", ascending=False).head(50)
            for _, r in crit.iterrows():
                criticas.append(_clean({
                    "obra":          str(r.get("obra", "")),
                    "pavimento":     str(r.get("floor", "")),
                    "modelo":        str(r.get("modelo", "")),
                    "local":         str(r.get("local", "")),
                    "dias_pendente": int(r.get("dias_pendente", 0)),
                    "nc":            int(r.get("nc", 0)),
                }))

    # ── Top modelos com pendencia (estado atual) ─────────────────────────────
    top_pendentes = []
    if not snap.empty:
        pend = snap[snap["status"] != "FINALIZADA"]
        if not pend.empty:
            g = (pend.groupby("modelo")
                 .agg(pendentes=("status", "count"), nc=("nc", "sum"))
                 .sort_values("pendentes", ascending=False).head(8).reset_index())
            for _, r in g.iterrows():
                top_pendentes.append(_clean({
                    "modelo":    str(r["modelo"]),
                    "pendentes": int(r["pendentes"]),
                    "nc":        int(r["nc"]),
                }))

    return {
        "obra":     obra or "Todas as obras",
        "periodo":  periodo,
        "intervalo": {"de": inicio.isoformat(), "ate": fim.isoformat()},
        "kpis": {
            # do periodo — mesma fonte da serie do grafico
            "total_insp":        total_periodo["total_insp"],
            "finalizada":        total_periodo["finalizada"],
            "em_andamento":      total_periodo["em_andamento"],
            "pct_finalizada":    total_periodo["pct_finalizada"],
            "nc_total":          total_periodo["nc_total"],
            "nc_pendentes":      total_periodo["nc_total"],
            # do estado atual — vem dos snapshots, independem do recorte
            "snap_nao_iniciada": int(kpis.get("snap_nao_iniciada", 0)),
            "snap_criticas":     int(kpis.get("snap_criticas", 0)),
            "snap_nc_pendentes": int(kpis.get("snap_nc_pendentes", 0)),
        },
        "sla": {
            "media_dias": float(sla.get("avg_dias_nao_iniciada", 0) or 0),
            "max_dias":   int(sla.get("max_dias_nao_iniciada", 0) or 0),
        },
        "serie":         serie,
        "granularidade": granularidade,
        "comparativo":   comparativo,
        "aging":         aging,
        "criticas":      criticas,
        "top_pendentes": top_pendentes,
        "dias_snapshot": int(hist["date_snapshot"].nunique()) if not hist.empty else 0,
    }


# ── Decoracao e Acabamentos ───────────────────────────────────────────────────

@app.get("/api/decoracao")
def decoracao(
    obra: str = Query(default=""),          # "" = todas
    disciplina: str = Query(default=""),
    status: str = Query(default=""),
    _usuario: str = Depends(usuario_atual),
):
    """Cronograma de acabamento: KPIs, Gantt por pavimento e alertas."""
    from fvs_dashboard.core.decoracao_engine import (
        DISC_COLORS, build_discipline_summary, build_floor_gantt,
        compute_kpis, load_decoracao,
    )

    if obra and obra not in OBRAS:
        raise HTTPException(404, f"Obra desconhecida: {obra}")

    try:
        df = load_decoracao(obra or None)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Cache Prevision indisponivel: {exc}")

    if df.empty:
        return {"obra": obra or "Todas as obras", "vazio": True, "kpis": {},
                "gantt": [], "disciplinas": [], "pavimentos": [], "alertas": [],
                "facetas": {"disciplinas": [], "status": []}, "intervalo": None}

    facetas = {
        "disciplinas": sorted(df["discipline"].dropna().unique().tolist()),
        "status": sorted(df["status"].dropna().unique().tolist()),
    }

    if disciplina:
        df = df[df["discipline"] == disciplina]
    if status:
        df = df[df["status"] == status]

    if df.empty:
        return {"obra": obra or "Todas as obras", "vazio": True, "kpis": {},
                "gantt": [], "disciplinas": [], "pavimentos": [], "alertas": [],
                "facetas": facetas, "intervalo": None}

    kpis = compute_kpis(df)

    # ── Gantt por pavimento ──────────────────────────────────────────────────
    gantt = []
    g = build_floor_gantt(df)
    for _, r in g.sort_values("floor_pos").iterrows():
        gantt.append(_clean({
            "pavimento":  str(r["floor_short"]),
            "obra":       str(r.get("obra", "")),
            "inicio":     r["start_dt"].date().isoformat(),
            "fim":        r["end_dt"].date().isoformat(),
            "atividades": int(r["n_ativs"]),
            "pct":        float(r["pct_medio"]),
            "status":     str(r["status"]),
            "finalizadas":   int(r.get("n_fin", 0)),
            "atrasadas":     int(r.get("n_atra", 0)),
            "disciplinas":   str(r.get("disciplines", "")),
        }))

    # ── Resumo por disciplina ────────────────────────────────────────────────
    disciplinas = []
    ds = build_discipline_summary(df)
    if not ds.empty:
        for _, r in ds.iterrows():
            nome = str(r["discipline"])
            disciplinas.append({
                "disciplina": nome,
                "total":      int(r["total"]),
                "pct":        float(r.get("pct_medio", 0) or 0),
                "cor":        DISC_COLORS.get(nome, "#95A5A6"),
            })

    # ── Avanco por pavimento ─────────────────────────────────────────────────
    pav = (df.groupby(["floor_short", "floor_pos"])
             .agg(pct=("pct", "mean"), n=("act_id", "count"))
             .reset_index().sort_values("floor_pos").head(25))
    pavimentos = [_clean({
        "pavimento": str(r["floor_short"]),
        "pct":       round(float(r["pct"]), 1),
        "atividades": int(r["n"]),
    }) for _, r in pav.iterrows()]

    # ── Alertas: deveria ter comecado e esta em 0% ───────────────────────────
    hoje = datetime.date.today()
    atrasadas = df[(df["start"] <= hoje) & (df["pct"] == 0)].copy()
    if not atrasadas.empty:
        atrasadas["dias"] = atrasadas["start"].apply(lambda d: (hoje - d).days)
        atrasadas = atrasadas.sort_values("dias", ascending=False).head(40)
    alertas = [_clean({
        "obra":       str(r["obra"]),
        "wbs":        str(r["wbs"]),
        "pavimento":  str(r["floor_short"]),
        "disciplina": str(r["discipline"]),
        "servico":    str(r["job_name"]),
        "inicio":     r["start"].isoformat(),
        "dias":       int(r["dias"]),
    }) for _, r in atrasadas.iterrows()] if not atrasadas.empty else []

    return {
        "obra": obra or "Todas as obras",
        "vazio": False,
        "kpis": {
            "total":        int(kpis.get("total", 0)),
            "finalizada":   int(kpis.get("finalizada", 0)),
            "em_andamento": int(kpis.get("em_andamento", 0)),
            "nao_iniciada": int(kpis.get("nao_iniciada", 0)),
            "atrasada":     int(kpis.get("atrasada", 0)),
            "pct_medio":    float(kpis.get("pct_medio", 0)),
            "proximas_30d": int(kpis.get("proximas_30d", 0)),
        },
        "gantt": gantt,
        "disciplinas": disciplinas,
        "pavimentos": pavimentos,
        "alertas": alertas,
        "facetas": facetas,
        "intervalo": {
            "de":  df["start"].min().isoformat(),
            "ate": df["end"].max().isoformat(),
        },
        "hoje": hoje.isoformat(),
    }


# ── Condicao do Tempo (Diario de Obra) ────────────────────────────────────────

# Contagens fixas anteriores a adocao do InMeta, vindas do controle interno
# da R21. Nao estao em lugar nenhum da API — precisam ser somadas ao total.
HISTORICO_PRE_INMETA = {"ENSOLARADO": 129, "NUBLADO": 77, "CHUVOSO": 42}

# A condicao do tempo e GERAL (mesmo ceu sobre os canteiros), nao por obra.
# Quando mais de uma obra registra RDO no mesmo dia, vale a primeira desta
# lista — assim o dia entra uma unica vez, sem duplicar a mesma realidade.
PRIORIDADE_DIARIO = ["Cape Town Residence", "Holmes Residence"]

CONDICOES = ["ENSOLARADO", "NUBLADO", "CHUVOSO"]


def _normalizar_tempo(valor: str) -> str:
    """
    Reduz classificacaoTempo as tres categorias operacionais.

    'TEMPESTADE' entrava aqui e saia sem classificacao — o dia sumia dos
    totais. Agora conta como CHUVOSO, junto com garoa/precipitacao.
    Valor vazio devolve "" e e reportado a parte como "sem condicao".
    """
    v = str(valor or "").upper().strip()
    if not v:
        return ""
    if "ENSOL" in v or v == "BOM" or "SOL" in v:
        return "ENSOLARADO"
    if "NUBLADO" in v or "PARCIAL" in v or "encoberto".upper() in v:
        return "NUBLADO"
    if "CHUV" in v or "TEMPEST" in v or "GAROA" in v or "PRECIPIT" in v:
        return "CHUVOSO"
    return v


@app.get("/api/tempo")
def tempo(_usuario: str = Depends(usuario_atual)):
    """
    Condicao do tempo consolidada — visao unica, nao por obra.

    Cada dia do calendario entra uma so vez: vale o RDO da obra de maior
    prioridade que registrou naquele dia. Ao total soma-se o historico fixo
    anterior ao InMeta.
    """
    caminho = Path(_ROOT) / "data" / "raw" / "inmeta_diario_raw.json"
    if not caminho.exists():
        return {
            "disponivel": False, "coletado_em": None,
            "prioridade": PRIORIDADE_DIARIO,
            "dias": [], "meses": [],
            "inmeta": {c: 0 for c in CONDICOES},
            "historico": HISTORICO_PRE_INMETA,
            "totais": dict(HISTORICO_PRE_INMETA),
            "cobertura": [],
        }

    import json as _json
    bruto = _json.loads(caminho.read_text(encoding="utf-8"))

    # data -> (condicao, obra de origem), respeitando a ordem de prioridade
    por_dia: dict[str, tuple[str, str]] = {}
    cobertura = []

    for obra_nome in PRIORIDADE_DIARIO:
        cfg = OBRAS.get(obra_nome)
        if not cfg:
            continue
        rdos = bruto.get(cfg["insp_key"]) or []

        # Dentro da mesma obra, o registro mais recente do dia prevalece
        dias_obra: dict[str, str] = {}
        for r in rdos:
            data = (r.get("dataInspecao") or "")[:10]
            if data:
                dias_obra[data] = _normalizar_tempo(r.get("classificacaoTempo"))

        novos = 0
        for data, condicao in dias_obra.items():
            if data not in por_dia:          # obra anterior tem prioridade
                por_dia[data] = (condicao, obra_nome)
                novos += 1

        cobertura.append({
            "obra": obra_nome,
            "dias_registrados": len(dias_obra),
            "dias_aproveitados": novos,      # o resto ja veio de obra prioritaria
        })

    dias = [{"data": d, "condicao": c, "origem": o}
            for d, (c, o) in sorted(por_dia.items())]

    inmeta = {c: sum(1 for (cond, _o) in por_dia.values() if cond == c) for c in CONDICOES}
    totais = {c: inmeta[c] + HISTORICO_PRE_INMETA.get(c, 0) for c in CONDICOES}

    # Dias com RDO mas sem condicao preenchida — em geral domingos e sabados
    # sem trabalho. Ficam fora da distribuicao (nao ha condicao a classificar),
    # mas sao reportados para o total de dias nao dar diferenca inexplicada.
    sem_condicao = sum(1 for (cond, _o) in por_dia.values() if not cond)
    outros = sum(1 for (cond, _o) in por_dia.values()
                 if cond and cond not in CONDICOES)

    meses: dict[str, dict[str, int]] = {}
    for d, (c, _o) in por_dia.items():
        alvo = meses.setdefault(d[:7], {k: 0 for k in CONDICOES})
        if c in alvo:
            alvo[c] += 1
    serie_meses = [{"mes": m, **v, "total": sum(v.values())}
                   for m, v in sorted(meses.items())]

    return {
        "disponivel": True,
        "coletado_em": bruto.get("collected_at"),
        "prioridade": PRIORIDADE_DIARIO,
        "dias": dias,
        "meses": serie_meses,
        "inmeta": inmeta,                    # dias unicos vindos do InMeta
        "historico": HISTORICO_PRE_INMETA,   # controle interno pre-InMeta
        "totais": totais,                    # historico + inmeta
        "cobertura": cobertura,
        "dias_com_rdo": len(por_dia),
        "sem_condicao": sem_condicao,
        "nao_classificados": outros,
    }


# ── Exportacao ────────────────────────────────────────────────────────────────

_ROTULO_PERIODO = {
    "Mes": "Ultimo mes", "Trimestre": "Ultimo trimestre",
    "Semestre": "Ultimo semestre", "Anual": "Este ano", "Tudo": "Todo o historico",
    "Personalizado": "Periodo personalizado",
}


@app.get("/api/export/auditoria")
def export_auditoria(
    obra: str = Query(default=""),
    periodo: str = Query(default="Tudo"),
    de: str = Query(default=""),
    ate: str = Query(default=""),
    formato: str = Query(default="excel", pattern="^(excel|pdf)$"),
    _usuario: str = Depends(usuario_atual),
):
    """Exporta a auditoria (Excel gerencial ou PDF executivo) do mesmo recorte da tela."""
    from fvs_dashboard.core.audit_exporter import export_audit_excel, export_audit_pdf

    mi, _todas, snap, hist, kpis, inicio, fim, _f = _dados_auditoria(obra, periodo, de, ate)
    rotulo = _ROTULO_PERIODO.get(periodo, periodo)
    nome_obra = obra or "Todas as obras"

    try:
        if formato == "pdf":
            conteudo = export_audit_pdf(
                monthly_insp=mi, kpis=kpis, obra=nome_obra, periodo_label=rotulo,
                date_start=inicio, date_end=fim, latest_snap=snap, hist_snap=hist,
            )
            media = "application/pdf"
            ext = "pdf"
        else:
            conteudo = export_audit_excel(
                monthly_insp=mi, kpis=kpis, obra=nome_obra, periodo_label=rotulo,
                date_start=inicio, date_end=fim, hist_snap=hist,
            )
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
    except Exception as exc:
        raise HTTPException(500, f"Falha ao gerar o relatorio: {exc}")

    nome = (f"Auditoria_R21_{_norm(nome_obra).replace(' ', '_')}_"
            f"{datetime.date.today():%Y%m%d}.{ext}")
    return StreamingResponse(
        iter([conteudo]), media_type=media,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"},
    )


@app.get("/api/export/fvs")
def export_fvs(
    obra: str = Query(...),
    formato: str = Query(default="excel", pattern="^(excel|pdf)$"),
    incluir_finalizadas: bool = Query(default=True),
    _usuario: str = Depends(usuario_atual),
):
    """Relatorio operacional de FVS — mesmos arquivos entregues pelo Streamlit."""
    from fvs_dashboard.core.exporter import export_excel, export_pdf

    _check_obra(obra)
    try:
        linhas = _dm.get_rows(obra)
        kpis = _dm.get_kpis(obra)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Cache indisponivel: {exc}")

    if not incluir_finalizadas:
        linhas = [r for r in linhas if r["status"] != "FINALIZADA"]

    try:
        if formato == "pdf":
            conteudo = export_pdf(rows=linhas, kpis=kpis, obra=obra)
            media, ext = "application/pdf", "pdf"
        else:
            conteudo = export_excel(rows=linhas, kpis=kpis, obra=obra,
                                    include_finalizadas=incluir_finalizadas)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
    except Exception as exc:
        raise HTTPException(500, f"Falha ao gerar o relatorio: {exc}")

    nome = f"FVS_{_norm(obra).replace(' ', '_')}_{datetime.date.today():%Y%m%d}.{ext}"
    return StreamingResponse(
        iter([conteudo]), media_type=media,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"},
    )


@app.get("/api/export/tempo")
def export_tempo(
    p1_de: str = Query(default=""),
    p1_ate: str = Query(default=""),
    p2_de: str = Query(default=""),
    p2_ate: str = Query(default=""),
    meses: int = Query(default=3, ge=0, le=12),
    _usuario: str = Depends(usuario_atual),
):
    """
    Excel da Condicao do Tempo no padrao das reunioes.

    Com p1/p2 informados, gera as tres pizzas: total + os dois periodos
    escolhidos na tela. Sem eles, cai nos ultimos meses com registro.
    """
    dados = tempo(_usuario=_usuario)
    if not dados.get("disponivel"):
        raise HTTPException(503, "Sem dados de diario de obra para exportar.")

    periodos = []
    for rotulo, de, ate in (("Período 1", p1_de, p1_ate), ("Período 2", p2_de, p2_ate)):
        if de and ate:
            try:
                if datetime.date.fromisoformat(de) > datetime.date.fromisoformat(ate):
                    raise HTTPException(400, f"{rotulo}: data inicial depois da final.")
            except ValueError:
                raise HTTPException(400, f"{rotulo}: datas devem ser AAAA-MM-DD.")
            periodos.append({"rotulo": rotulo, "de": de, "ate": ate})

    xlsx = build_tempo_report(dados, periodos=periodos or None, n_meses=meses)
    nome = f"Diario_do_Tempo_Obras_{datetime.date.today():%Y%m%d}.xlsx"
    return StreamingResponse(
        iter([xlsx]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"},
    )


@app.get("/api/export/backlog")
def export_backlog(
    obra: str = Query(...),
    status: list[str] = Query(default=[]),
    modelo: str = Query(default=""),
    pavimento: str = Query(default=""),
    busca: str = Query(default=""),
    _usuario: str = Depends(usuario_atual),
):
    """Excel do backlog com os mesmos filtros da tela."""
    _check_obra(obra)
    try:
        todas = [_clean(r) for r in _dm.get_rows(obra)]
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Cache indisponivel: {exc}")

    linhas = filtrar_rows(todas, status, modelo, pavimento, busca)

    # Descricao legivel dos filtros (vai no cabecalho da planilha)
    partes = []
    validos = [s for s in status if s in STATUS_VALIDOS]
    partes.append(
        "Status: " + (", ".join(_ROTULO_STATUS[s] for s in validos) if validos else "todos")
    )
    if modelo:
        partes.append(f"Modelo: {modelo}")
    if pavimento:
        partes.append(f"Pavimento: {pavimento}")
    if busca:
        partes.append(f'Busca: "{busca}"')
    descricao = "  |  ".join(partes)

    xlsx = build_backlog_report(linhas, obra, descricao, total_geral=len(todas))

    # Nome do arquivo: obra + status + data
    slug_obra = _norm(obra).replace(" ", "_")
    slug_status = "_".join(s.lower() for s in validos) if validos else "todos"
    nome = f"FVS_Backlog_{slug_obra}_{slug_status}_{datetime.date.today():%Y%m%d}.xlsx"

    return StreamingResponse(
        iter([xlsx]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"},
    )
