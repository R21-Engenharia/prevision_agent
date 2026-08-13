"""
scripts/coletar_rup_mensal.py
=============================
Série MENSAL de RUP por célula, para análise por janela de tempo.

Para cada mês (YYYY-MM) e cada célula (disciplina):
  • Hh        = efetivo do RDO no mês (rup.parser_rdo), por disciplina;
  • Produção  = Σ [ qtd_orçada Sienge × realized_points do Prevision naquele mês ].

A cffTable do Prevision guarda o % realizado MÊS A MÊS (realized_points); é isso
que permite recalcular a RUP de qualquer janela (mês, 6m, 12m, obra) somando só
os meses da janela — nunca filtrando uma RUP acumulada.

Saída: data/rup_mensal_{project_id}.json
    { "obra", "project_id", "celulas": { disc: { "YYYY-MM": {hh, producao} } } }

Executar (a partir de prevision_agent/), com PREVISION_* no ambiente:
    python scripts/coletar_rup_mensal.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
import time
from collections import defaultdict
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
from rup.depara import disciplinas_de
from rup.parser_rdo import registros_do_rdo

DATA = _ROOT / "data"
_ME = 479
_RE_DIRETOS = re.compile(r"custos\s+diretos", re.IGNORECASE)


def _disc(txt: str) -> str | None:
    d = disciplinas_de(txt)
    return sorted(d)[0] if d else None


def _exec(cli: GraphQLClient, q: str, tent: int = 4):
    for t in range(tent):
        try:
            return cli.execute(q)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                time.sleep(1.5 * (t + 1)); continue
            raise
    raise RuntimeError("Prevision instável (5xx).")


def _cff_rows(cli: GraphQLClient, pid: int) -> list[dict]:
    d = _exec(cli, f'{{ me(id:{_ME}){{ project(id:{pid}){{ budgetReports {{ id name }} }} }} }}')
    rid = next((r["id"] for r in d["me"]["project"]["budgetReports"] or []
                if _RE_DIRETOS.search(r.get("name") or "") and "indireto" not in (r.get("name") or "").lower()), None)
    if not rid:
        return []
    d = _exec(cli, f'{{ me(id:{_ME}){{ project(id:{pid}){{ budgetReport(id:{rid}){{ newCffTable }} }} }} }}')
    return (d["me"]["project"]["budgetReport"]["newCffTable"] or {}).get("rows", [])


def _producao_mensal(pid: int, rows: list[dict]) -> dict[str, dict[str, float]]:
    """disc -> mês -> produção (qty Sienge × realized_points do mês)."""
    eap = {str(e["referencia_sienge"]): e for e in
           json.loads((DATA / f"eap_{pid}.json").read_text(encoding="utf-8"))["itens"]
           if e.get("referencia_sienge")}
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        b = row.get("budget_item")
        if not isinstance(b, dict) or b.get("group_type") != "service":
            continue
        e = eap.get(str(b.get("reference_id")))
        if not e or not e.get("mao_de_obra") or not e.get("qtd_orcada"):
            continue
        d = _disc(e.get("descricao", ""))
        if not d:
            continue
        for mes, frac in (row.get("realized_points") or {}).items():
            out[d][mes[:7]] += e["qtd_orcada"] * frac
    return out


def _hh_mensal(obra: str, insp_key: str) -> dict[str, dict[str, float]]:
    """disc -> mês -> Hh (RDO)."""
    raw = json.loads((DATA / "raw" / "inmeta_diario_raw.json").read_text(encoding="utf-8"))
    ids = {r["_id"] for r in raw[insp_key]}
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for fp in glob.glob(str(DATA / "raw" / "rdo_detalhe" / "*.json")):
        if Path(fp).stem not in ids:
            continue
        for r in registros_do_rdo(json.loads(Path(fp).read_text(encoding="utf-8")), obra):
            d = _disc(r["fvs_nome"])
            if d:
                out[d][r["data"][:7]] += r["hh_total"]
    return out


def main() -> int:
    cli = GraphQLClient(load_config())
    for obra, cfg in OBRAS.items():
        pid, insp = cfg["prevision_id"], cfg["insp_key"]
        print(f"\n{obra} (projeto {pid})")
        prod = _producao_mensal(pid, _cff_rows(cli, pid))
        hh = _hh_mensal(obra, insp)
        celulas: dict[str, dict[str, dict]] = defaultdict(dict)
        for d in set(prod) | set(hh):
            meses = set(prod.get(d, {})) | set(hh.get(d, {}))
            for m in meses:
                celulas[d][m] = {
                    "hh": round(hh.get(d, {}).get(m, 0.0), 1),
                    "producao": round(prod.get(d, {}).get(m, 0.0), 2),
                }
        out = DATA / f"rup_mensal_{pid}.json"
        out.write_text(json.dumps({"obra": obra, "project_id": pid, "celulas": celulas},
                                  ensure_ascii=False), encoding="utf-8")
        print(f"  {len(celulas)} células · série mensal salva em {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
