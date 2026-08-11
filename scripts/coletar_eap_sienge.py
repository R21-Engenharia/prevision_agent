"""
scripts/coletar_eap_sienge.py
=============================
Monta a EAP de serviços com QUANTIDADE EXECUTADA, unindo os três sistemas:

  • Prevision (cffTable "Custos Diretos") → estrutura + % realizado
      (soma dos realized_points de cada linha), + reference_id (código Sienge).
  • Sienge (building-cost-estimations sheet "Custos Diretos") → quantity +
      unitOfMeasure, casando por item.id == reference_id do Prevision.

  qtd_executada(item) = quantity_Sienge × %realizado_Prevision   (decisão do Elrik)

Saída: data/eap_{project_id}.json por obra — a base do denominador da RUP.

Executar (a partir de prevision_agent/), com PREVISION_* e SIENGE_* no ambiente:
    python scripts/coletar_eap_sienge.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")

from client.graphql_client import GraphQLClient
from config.settings import load_config
from fvs_dashboard.core.data_manager import OBRAS
from rup.sienge_client import SiengeClient

DATA = _ROOT / "data"
_ME = 479
_RE_DIRETOS = re.compile(r"custos\s+diretos", re.IGNORECASE)


def _exec(cli: GraphQLClient, query: str, tentativas: int = 4):
    for t in range(tentativas):
        try:
            return cli.execute(query)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                time.sleep(1.5 * (t + 1))
                continue
            raise
    raise RuntimeError("Prevision instável (5xx).")


def _report_diretos(cli: GraphQLClient, pid: int) -> str | None:
    d = _exec(cli, f'{{ me(id:{_ME}){{ project(id:{pid}){{ budgetReports {{ id name }} }} }} }}')
    for r in d["me"]["project"]["budgetReports"] or []:
        nome = r.get("name") or ""
        if _RE_DIRETOS.search(nome) and "indireto" not in nome.lower():
            return r["id"]
    return None


def _prevision_eap(cli: GraphQLClient, pid: int, rid: str) -> list[dict]:
    d = _exec(cli, f'{{ me(id:{_ME}){{ project(id:{pid}){{ '
                   f'budgetReport(id:{rid}){{ newCffTable }} }} }} }}')
    cff = d["me"]["project"]["budgetReport"]["newCffTable"] or {}
    itens = []
    for row in cff.get("rows", []):
        b = row.get("budget_item")
        if not isinstance(b, dict) or b.get("group_type") != "service" or b.get("deleted_at"):
            continue
        realizado = sum((row.get("realized_points") or {}).values())
        itens.append({
            "code": b.get("code"),
            "descricao": b.get("description"),
            "unidade": b.get("unit"),
            "referencia_sienge": str(b.get("reference_id")) if b.get("reference_id") else None,
            "mao_de_obra": bool(re.match(r"\s*MOE\b", str(b.get("description") or ""), re.IGNORECASE)),
            "pct_realizado": round(min(1.0, max(0.0, realizado)), 4),
        })
    return itens


def main() -> int:
    prev = GraphQLClient(load_config())
    sng = SiengeClient()
    if not sng.configurado:
        print("Sienge não configurado (SIENGE_*). Abortando.")
        return 1

    for obra, cfg in OBRAS.items():
        pid = cfg["prevision_id"]
        bid, sid = cfg.get("sienge_building_id"), cfg.get("sienge_sheet_id")
        print(f"\n{obra}  (Prevision {pid} · Sienge building {bid}/sheet {sid})")

        rep = _report_diretos(prev, pid)
        if not rep:
            print("  ! sem report 'Custos Diretos' no Prevision — pulando.")
            continue
        eap = _prevision_eap(prev, pid, rep)
        print(f"  Prevision: {len(eap)} serviços")

        sitems = sng.fetch_orcamento_items(bid, sid)
        qmap = {str(i.get("id")): i for i in sitems}
        print(f"  Sienge: {len(sitems)} itens de orçamento")

        casados = 0
        for e in eap:
            si = qmap.get(e["referencia_sienge"] or "")
            if si:
                casados += 1
                q = si.get("quantity")
                e["qtd_orcada"] = q
                e["unidade_sienge"] = si.get("unitOfMeasure")
                e["wbs_sienge"] = si.get("wbsCode")
                e["qtd_executada"] = (round(q * e["pct_realizado"], 3)
                                      if isinstance(q, (int, float)) else None)
            else:
                e["qtd_orcada"] = e["unidade_sienge"] = e["wbs_sienge"] = e["qtd_executada"] = None

        out = DATA / f"eap_{pid}.json"
        out.write_text(json.dumps({
            "obra": obra, "project_id": pid, "sienge_building_id": bid,
            "itens": eap,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        moe = sum(1 for e in eap if e["mao_de_obra"])
        comq = sum(1 for e in eap if e.get("qtd_executada"))
        print(f"  casados Prevision↔Sienge: {casados}/{len(eap)} · MOE {moe} · "
              f"com qtd executada {comq}")
        print(f"  → {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
