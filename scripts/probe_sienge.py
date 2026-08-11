"""
scripts/probe_sienge.py
=======================
Sondagem inicial da API do Sienge — SEM cálculo ainda, só descoberta:
  1. testa a autenticação;
  2. lista as obras (building-projects) para achar os IDs Sienge das nossas;
  3. varre endpoints candidatos de ORÇAMENTO (quantidade + unidade) e de
     MEDIÇÃO (quantidade executada = o denominador da RUP), mostrando status
     e os campos do 1º item — para a gente mapear onde a quantidade mora.

Executar (a partir de prevision_agent/), com SIENGE_* no ambiente:
    python scripts/probe_sienge.py
"""
from __future__ import annotations

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

sys.stdout.reconfigure(encoding="utf-8")

from rup.sienge_client import SiengeClient


def _amostra(body) -> str:
    itens = body.get("results") if isinstance(body, dict) else body
    if isinstance(itens, list) and itens:
        return "campos 1º item: " + ", ".join(list(itens[0].keys())[:16])
    if isinstance(body, dict):
        return "keys: " + ", ".join(list(body.keys())[:16])
    return str(body)[:120]


def _sonda(cli: SiengeClient, path: str, params: dict | None = None, bulk: bool = False):
    tag = "bulk:" if bulk else ""
    try:
        r = cli.get(path, params=params, bulk=bulk, timeout=40)
    except Exception as exc:  # noqa: BLE001
        print(f"  [ERR] {tag}{path} → {exc}")
        return None
    if r.status_code == 200:
        try:
            body = r.json()
        except Exception:
            body = r.text[:120]
        n = len(body.get("results", [])) if isinstance(body, dict) else (
            len(body) if isinstance(body, list) else "?")
        print(f"  [200] {tag}{path}  (n={n})  {_amostra(body)}")
        return body
    print(f"  [{r.status_code}] {tag}{path}  {r.text[:120]}")
    return None


def main() -> int:
    cli = SiengeClient()
    if not cli.configurado:
        print("Sienge NÃO configurado. Defina no .env / Render:")
        print("  SIENGE_SUBDOMAIN=<subdominio>   (ex.: r21)")
        print("  SIENGE_API_USER=<usuario da API de integração>")
        print("  SIENGE_API_PASSWORD=<senha>")
        return 1

    print(f"Base: {cli.base}\n")
    ok, detalhe = cli.ping()
    print(f"Auth: {'OK' if ok else 'FALHOU'} — {detalhe}\n")
    if not ok:
        return 1

    print("── 1. Obras (building-projects / enterprises) ───────────────────────")
    obras = _sonda(cli, "building-projects", {"limit": 20})
    _sonda(cli, "enterprises", {"limit": 5})
    if isinstance(obras, dict):
        for o in obras.get("results", [])[:20]:
            print(f"      obra id={o.get('id')}  {o.get('name')}")

    print("\n── 2. Unidades de medida / bases de custo ───────────────────────────")
    _sonda(cli, "unit-of-measurements", {"limit": 3})
    _sonda(cli, "cost-databases", {"limit": 3})

    print("\n── 3. ORÇAMENTO (quantidade + unidade) — candidatos ─────────────────")
    for p in ["building-cost-estimations", "cost-estimations",
              "building-cost-estimation-resources", "sheets"]:
        _sonda(cli, p, {"limit": 3})

    print("\n── 4. MEDIÇÃO (quantidade executada) — candidatos ───────────────────")
    for p in ["measurements", "supply-contracts/measurements",
              "building-cost-estimations/measurements", "work-progress"]:
        _sonda(cli, p, {"limit": 3})

    print("\n── 5. Bulk-data (grandes volumes) ───────────────────────────────────")
    for p in ["cost-estimation-items", "measurements", "movements"]:
        _sonda(cli, p, {"limit": 3}, bulk=True)

    print("\n(descoberta — nenhum cálculo feito. Próximo: mapear o campo de "
          "quantidade e casar pelo código Sienge = reference_id do de-para.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
