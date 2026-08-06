"""
Coleta o grafo de dependências (precedência) do Prevision.
==========================================================
Para cada atividade, puxa predecessorsPage (predecessor, timeOperation, delay)
e salva o edge list + progresso em data/raw/{pid}_dependencies_raw.json.
É a espinha dorsal da análise causal do Agente Inteligente.

Executar (a partir de prevision_agent/):
    python scripts/collect_dependencies.py            # todas as obras
    python scripts/collect_dependencies.py 10223      # só um project_id

Precisa de PREVISION_TOKEN (env ou .env). ~8-10 min por obra.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

TOKEN = os.getenv("PREVISION_TOKEN")
if not TOKEN and (_ROOT / ".env").exists():
    for _l in (_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if _l.startswith("PREVISION_TOKEN="):
            TOKEN = _l.split("=", 1)[1].strip().strip('"')

ENDPOINT = "https://api.prevision.com.br/graphql"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
           "UserAuthorization": f"token {TOKEN}"}
PROJECTS = [10223, 18992]   # Cape Town, Holmes

FLOOR_Q = ('{ me(id:479){ project(id:%d){ floorsPage(first:1%s){ '
           'pageInfo{hasNextPage endCursor} edges{ node{ id }}}}}}')
ACT_Q = ('{ me(id:479){ project(id:%d){ floorsPage(first:1%s){ edges{ node{ '
         'activitiesPage(first:10%s){ pageInfo{hasNextPage endCursor} edges{ node{ '
         'id wbsCode percentageCompleted expectedPercentageCompleted startAt '
         'predecessorsPage(first:8){ edges{ node{ timeOperation delay predecessor{ id }}}}'
         '}}}}}}}}}')


def _run(q: str, tries: int = 4):
    last = None
    for _ in range(tries):
        try:
            r = httpx.post(ENDPOINT, json={"query": q}, headers=HEADERS, timeout=90).json()
            if "error" in r or "errors" in r:
                last = json.dumps(r)[:150]; time.sleep(1.2); continue
            return r
        except Exception as ex:
            last = str(ex)[:150]; time.sleep(2)
    print("  FALHA:", last, flush=True)
    return None


def coletar(pid: int) -> None:
    acts: dict = {}
    edges: dict = {}
    floor_cur = None
    nf = 0
    while True:
        fac = ', after:"%s"' % floor_cur if floor_cur else ""
        fr = _run(FLOOR_Q % (pid, fac))
        if not fr:
            break
        fp = fr["data"]["me"]["project"]["floorsPage"]
        if not fp["edges"]:
            break
        nf += 1
        acur = None
        while True:
            aac = ', after:"%s"' % acur if acur else ""
            ar = _run(ACT_Q % (pid, fac, aac))
            if not ar:
                break
            ap = ar["data"]["me"]["project"]["floorsPage"]["edges"][0]["node"]["activitiesPage"]
            for e in ap["edges"]:
                a = e["node"]; aid = a["id"]
                acts[aid] = {"wbs": a["wbsCode"], "pct": a.get("percentageCompleted"),
                             "exp": a.get("expectedPercentageCompleted"), "start": a.get("startAt")}
                es = [(p["node"]["predecessor"]["id"], p["node"]["timeOperation"], p["node"]["delay"])
                      for p in a["predecessorsPage"]["edges"] if p["node"].get("predecessor")]
                if es:
                    edges[aid] = es
            if ap["pageInfo"]["hasNextPage"]:
                acur = ap["pageInfo"]["endCursor"]
            else:
                break
        if nf % 8 == 0:
            print(f"  [{pid}] {nf} pav, {len(acts)} ativ, {len(edges)} c/ predecessor", flush=True)
        if fp["pageInfo"]["hasNextPage"]:
            floor_cur = fp["pageInfo"]["endCursor"]
        else:
            break

    out = _ROOT / "data" / "raw" / f"{pid}_dependencies_raw.json"
    out.write_text(json.dumps({"project_id": pid, "activities": acts, "edges": edges},
                              ensure_ascii=False), encoding="utf-8")
    print(f"  [{pid}] SALVO: {nf} pav, {len(acts)} ativ, "
          f"{sum(len(v) for v in edges.values())} arestas", flush=True)


def main() -> int:
    if not TOKEN:
        print("ERRO: PREVISION_TOKEN não definido.")
        return 1
    alvos = [int(sys.argv[1])] if len(sys.argv) > 1 else PROJECTS
    for pid in alvos:
        print(f"Coletando dependências do projeto {pid}...", flush=True)
        coletar(pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
