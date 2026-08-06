"""
Gera Pendências Inteligentes a partir do grafo de dependências + progresso.
===========================================================================
Executar (a partir de prevision_agent/):
    python scripts/gerar_pendencias.py --dry-run    # só imprime, não grava
    python scripts/gerar_pendencias.py              # grava no Supabase

Em produção roda agendado (como os outros coletores). O --dry-run serve para
validar a lógica sem tocar no banco.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from agente.motor import analisar
from agente.perguntas import perguntas_para

# obra -> project_id do Prevision (espelha OBRAS do data_manager)
OBRA_PID = {"Cape Town Residence": 10223, "Holmes Residence": 18992}


def _carregar_grafo(pid: int) -> dict | None:
    caminho = _ROOT / "data" / "raw" / f"{pid}_dependencies_raw.json"
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def _mapa_pavimento(pid: int) -> dict[str, str]:
    """
    activity_id -> nome REAL do pavimento (_floor_name), do cache de atividades.
    O prefixo do WBS ("38.90") é a _floor_position (índice interno), não o andar.
    """
    caminho = _ROOT / "data" / "raw" / f"{pid}_activities_raw.json"
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {a["id"]: a.get("_floor_name", "").strip()
            for a in dados.get("activities_list", []) if a.get("_floor_name")}


def _mapa_jobs(pid: int) -> dict[str, list]:
    """activity_id -> [jobs pendentes {name, pct}], do cache jobs_raw."""
    caminho = _ROOT / "data" / "raw" / f"{pid}_jobs_raw.json"
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    mapa: dict[str, list] = {}
    for a in dados.get("activities_list", []):
        pend = [{"name": j.get("name", ""), "pct": j.get("percentageCompleted") or 0}
                for j in (a.get("jobs") or [])
                if (j.get("percentageCompleted") or 0) < 100]
        if pend:
            pend.sort(key=lambda x: x["pct"])          # o mais atrasado primeiro
            mapa[a["id"]] = pend[:6]
    return mapa


# Acima deste avanço físico, o que falta costuma ser só o preenchimento da FVS,
# não obra. Sinaliza para o usuário decidir (item validado pelo Elrik).
LIMIAR_PROVAVEL_FVS = 80


def gerar(obra: str) -> list:
    pid = OBRA_PID[obra]
    dados = _carregar_grafo(pid)
    if not dados:
        print(f"  [{obra}] sem grafo de dependências coletado — pule/rode o coletor.")
        return []
    pend = analisar(dados, obra)

    # Enriquecer: pavimento REAL, serviço específico (job) e flag "só FVS".
    jobs = _mapa_jobs(pid)
    pav = _mapa_pavimento(pid)
    for p in pend:
        nome_pav = pav.get(p.activity_id)
        if nome_pav:
            p.pavimento = nome_pav
        p.causa_raiz["jobs_pendentes"] = jobs.get(p.activity_id, [])
        p.causa_raiz["provavel_so_fvs"] = p.pct_real >= LIMIAR_PROVAVEL_FVS
        # dá pavimento real aos serviços travados (para a conversa mostrar
        # "trava REBOCO INTERNO no 17º", não "trava o 21")
        for t in p.causa_raiz.get("trava", []):
            t["pavimento"] = pav.get(t.get("id", ""), "")
    return pend


def imprimir(obra: str, pendencias: list) -> None:
    print(f"\n=== {obra}: {len(pendencias)} pendências (raízes) ===")
    for p in pendencias[:12]:
        ctx = {
            "wbs": p.wbs_code, "servico": p.servico, "pavimento": p.pavimento,
            "pct_real": p.pct_real, "pct_esperado": p.pct_esperado,
            "impacto": p.impacto,
            "predecessor": p.causa_raiz.get("predecessor_wbs", ""),
            "pred_pct": p.causa_raiz.get("pred_pct", 0),
        }
        cab = f"[{p.categoria}] {p.wbs_code}  {p.pct_real:.0f}%/{p.pct_esperado:.0f}%"
        if p.categoria == "atraso_proprio":
            cab += f"  — trava {p.impacto} serviço(s) a jusante"
        print(f"\n  {cab}")
        for q in perguntas_para(p.categoria, ctx):
            print(f"      • {q}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="não grava no banco")
    ap.add_argument("--obra", default=None, help="processar só uma obra")
    args = ap.parse_args()

    obras = [args.obra] if args.obra else list(OBRA_PID)
    total = 0
    for obra in obras:
        pend = gerar(obra)
        total += len(pend)
        if args.dry_run:
            imprimir(obra, pend)
        else:
            from agente.persistencia import salvar_pendencias
            salvos = salvar_pendencias(obra, pend)
            print(f"  [{obra}] {salvos} pendências gravadas/atualizadas.")

    print(f"\nTotal: {total} pendências." + ("  (dry-run — nada gravado)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
