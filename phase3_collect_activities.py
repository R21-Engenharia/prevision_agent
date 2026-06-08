"""
Fase 3 — Coleta completa de Activities.

Estratégia:
  - Para cada projeto (Cape Town 10223, Holmes 18992):
    - Paginar floorsPage (all floors)
    - Para cada floor: paginar activitiesPage (page_size=20, retry=3)
    - Coletar todos os campos seguros confirmados
  - Salvar JSON incremental (checkpoint por floor)
  - Relatório final com métricas

Campos seguros Activity (confirmados 2026-05-13):
  id, wbsCode, floorId, floorNameWithActivityPart,
  percentageCompleted, expectedPercentageCompleted,
  hasQualityAssociations, hasJobs, part,
  startAt, endAt, updatedAt, workDuration, budgetCost

NUNCA usar: name, status, position, service, floor, qualityAssociations,
            presignS3Url, collectionChannel
"""
import io, os, sys, json, time
os.environ.setdefault("PYTHONUTF8", "1")
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from pathlib import Path
from datetime import datetime

token = os.environ.get("PREVISION_TOKEN")
if not token:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("PREVISION_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
if not token:
    print("ERRO: PREVISION_TOKEN nao encontrado em env nem em .env")
    sys.exit(1)

ENDPOINT = "https://api.prevision.com.br/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "UserAuthorization": f"token {token}",
}

PROJECTS = [
    {"id": 10223, "name": "CAPE TOWN RESIDENCE"},
    {"id": 18992, "name": "HOLMES RESIDENCE"},
]

PAGE_SIZE_FLOORS   = 20
PAGE_SIZE_ACTS     = 20   # menor = menos chance de timeout por floor denso
TIMEOUT_ACTS       = 90   # segundos por request de activities
TIMEOUT_FLOORS     = 30
RETRY_LIMIT        = 3
RETRY_DELAY        = 5    # segundos entre retries

DATA_DIR = Path("data/raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─── helpers ─────────────────────────────────────────────────────────────────

def post_gql(query: str, timeout: int = 30) -> dict | None:
    """POST GraphQL — retorna body dict ou None em caso de erro."""
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as c:
            resp = c.post(ENDPOINT, json={"query": query}, headers=HEADERS)
        if resp.status_code != 200:
            return None
        body = resp.json()
        if body.get("errors"):
            return None
        return body
    except Exception:
        return None


def fetch_with_retry(query: str, timeout: int, label: str) -> dict | None:
    for attempt in range(1, RETRY_LIMIT + 1):
        result = post_gql(query, timeout)
        if result is not None:
            return result
        if attempt < RETRY_LIMIT:
            print(f"    ⚠ retry {attempt}/{RETRY_LIMIT-1} — {label}")
            time.sleep(RETRY_DELAY)
    print(f"    ✗ FALHOU após {RETRY_LIMIT} tentativas — {label}")
    return None


# ─── queries ─────────────────────────────────────────────────────────────────

FLOORS_QUERY = """
{{ me(id: 479) {{
  project(id: {project_id}) {{
    floorsPage(first: {page_size}, after: {cursor}) {{
      totalCount
      pageInfo {{ hasNextPage endCursor }}
      edges {{ node {{
        id
        name
        position
        tag
        startAt
        endAt
        hasQualityLocalsAssociations
        activitiesPage {{ totalCount }}
      }}}}
    }}
  }}
}}}}
"""

ACTIVITIES_QUERY = """
{{ me(id: 479) {{
  project(id: {project_id}) {{
    floorsPage(first: 1, after: {floor_cursor}) {{
      edges {{ node {{
        id
        activitiesPage(first: {page_size}, after: {cursor}) {{
          totalCount
          pageInfo {{ hasNextPage endCursor }}
          edges {{ node {{
            id
            wbsCode
            floorId
            floorNameWithActivityPart
            percentageCompleted
            expectedPercentageCompleted
            hasQualityAssociations
            hasJobs
            part
            startAt
            endAt
            updatedAt
            workDuration
            budgetCost
          }}}}
        }}
      }}}}
    }}
  }}
}}}}
"""

# alternativa: acessa activities do floor diretamente pelo ID do floor
# usando floorsPage com after=cursor para pular até o floor certo
# Melhor: usar after do cursor do floor anterior, avançando 1 a 1

# Query mais eficiente: iterar activities direto por floor_id usando cursor
ACTIVITIES_BY_FLOOR_QUERY = """
{{ me(id: 479) {{
  project(id: {project_id}) {{
    floorsPage(first: 1, after: "{floor_prev_cursor}") {{
      edges {{ node {{
        id
        activitiesPage(first: {page_size}{after_clause}) {{
          totalCount
          pageInfo {{ hasNextPage endCursor }}
          edges {{ node {{
            id
            wbsCode
            floorId
            floorNameWithActivityPart
            percentageCompleted
            expectedPercentageCompleted
            hasQualityAssociations
            hasJobs
            part
            startAt
            endAt
            updatedAt
            workDuration
            budgetCost
          }}}}
        }}
      }}}}
    }}
  }}
}}}}
"""

# Mais simples: query activities com floorsPage filtrando por posição
# Mas o servidor não tem filter por floorId em activitiesPage
# Vamos usar a abordagem de paginar todos os floors e para cada floor
# paginar as activities usando o cursor do floor

def collect_floors(project_id: int) -> list[dict]:
    """Coleta todos os floors do projeto."""
    floors = []
    cursor = "null"
    page = 0
    while True:
        page += 1
        q = FLOORS_QUERY.format(
            project_id=project_id,
            page_size=PAGE_SIZE_FLOORS,
            cursor=cursor,
        )
        body = fetch_with_retry(q, TIMEOUT_FLOORS, f"floors p{page}")
        if not body:
            print(f"  ✗ Falhou ao coletar floors página {page}")
            break
        conn = body["data"]["me"]["project"]["floorsPage"]
        for edge in conn["edges"]:
            floors.append(edge["node"])
        pi = conn["pageInfo"]
        total = conn["totalCount"]
        print(f"  floors: {len(floors)}/{total} (p{page})")
        if not pi["hasNextPage"]:
            break
        cursor = f'"{pi["endCursor"]}"'
    return floors


def build_floor_cursors(project_id: int, floors: list[dict]) -> dict[str, str]:
    """
    Para cada floor, precisamos do cursor "anterior" para usar floorsPage(first:1, after: prev_cursor).
    O floor no índice 0 usa after="" (null), floor 1 usa o cursor do floor 0, etc.
    Mas como o servidor retorna cursors de floor da página de floors, precisamos
    re-paginar floors 1-a-1 para capturar cada cursor individualmente.

    Alternativa mais simples: usar floorsPage sem paginação e acessar
    activitiesPage diretamente por índice de posição... mas o servidor não suporta.

    Estratégia: usar floorsPage(first:1) iterando via after cursor para ir floor por floor.
    O cursor do edge é capturado via a query de floors.
    """
    # Não precisamos re-paginar: os floors já foram coletados com seus IDs.
    # Vamos usar uma abordagem diferente: para cada floor, fazer uma query
    # que retorna as activities do floor específico usando um hack:
    # floorsPage(first:N) filtra por posição implícita.
    #
    # Abordagem CORRETA: usar a query de activities com after cursor do floor.
    # Precisamos dos edge cursors da paginação de floors.
    #
    # Vamos re-paginar floors com pageInfo, capturando edge cursors.
    pass


def collect_activities_for_floor_by_index(
    project_id: int,
    floor_index: int,
    floor_id: str,
    total_activities: int,
) -> list[dict]:
    """
    Coleta activities de um floor específico.
    Usa floorsPage(first: floor_index+1) e pega o último edge, depois
    pagina activitiesPage daquele floor.

    NOTA: Esta abordagem carrega floor_index+1 floors a cada request — ineficiente
    para floors com index alto. Usar apenas para floors com index < 10.
    Alternativa para floors com index >= 10: usar cursor do floor.
    """
    activities = []
    act_cursor = "null"
    act_page = 0

    while True:
        act_page += 1
        after_clause = f", after: {act_cursor}" if act_cursor != "null" else ""

        # Query: pega o floor pelo índice (first: index+1, sem after) e pega o último
        q = f"""{{ me(id: 479) {{
          project(id: {project_id}) {{
            floorsPage(first: {floor_index + 1}) {{
              edges {{ node {{
                id
                activitiesPage(first: {PAGE_SIZE_ACTS}{after_clause}) {{
                  totalCount
                  pageInfo {{ hasNextPage endCursor }}
                  edges {{ node {{
                    id wbsCode floorId floorNameWithActivityPart
                    percentageCompleted expectedPercentageCompleted
                    hasQualityAssociations hasJobs part
                    startAt endAt updatedAt workDuration budgetCost
                  }}}}
                }}
              }}}}
            }}
          }}
        }}}}"""

        body = fetch_with_retry(q, TIMEOUT_ACTS, f"floor[{floor_index}] acts p{act_page}")
        if not body:
            break

        edges_floor = body["data"]["me"]["project"]["floorsPage"]["edges"]
        if not edges_floor:
            break
        # pega o floor no índice correto (último da lista retornada)
        target_floor = edges_floor[floor_index] if floor_index < len(edges_floor) else edges_floor[-1]
        act_conn = target_floor["node"]["activitiesPage"]

        for ae in act_conn["edges"]:
            activities.append(ae["node"])

        pi = act_conn["pageInfo"]
        if not pi["hasNextPage"]:
            break
        act_cursor = f'"{pi["endCursor"]}"'

    return activities


def collect_activities_via_cursor(
    project_id: int,
    floor_prev_cursor: str,
    floor_id: str,
    total_activities: int,
) -> list[dict]:
    """
    Coleta activities de um floor usando floorsPage(first:1, after: prev_cursor).
    prev_cursor = cursor do floor ANTERIOR (edge cursor da paginação de floors).
    Para o primeiro floor, prev_cursor = "" (sem after).
    """
    activities = []
    act_cursor = "null"
    act_page = 0

    while True:
        act_page += 1
        after_clause = f', after: "{act_cursor}"' if act_cursor != "null" else ""
        after_floor  = f', after: "{floor_prev_cursor}"' if floor_prev_cursor else ""

        q = f"""{{ me(id: 479) {{
          project(id: {project_id}) {{
            floorsPage(first: 1{after_floor}) {{
              edges {{ node {{
                id
                activitiesPage(first: {PAGE_SIZE_ACTS}{after_clause}) {{
                  totalCount
                  pageInfo {{ hasNextPage endCursor }}
                  edges {{ node {{
                    id wbsCode floorId floorNameWithActivityPart
                    percentageCompleted expectedPercentageCompleted
                    hasQualityAssociations hasJobs part
                    startAt endAt updatedAt workDuration budgetCost
                  }}}}
                }}
              }}}}
            }}
          }}
        }}}}"""

        body = fetch_with_retry(q, TIMEOUT_ACTS, f"floor {floor_id} acts p{act_page}")
        if not body:
            break

        edges_floor = body["data"]["me"]["project"]["floorsPage"]["edges"]
        if not edges_floor:
            break
        act_conn = edges_floor[0]["node"]["activitiesPage"]
        retrieved_floor_id = edges_floor[0]["node"]["id"]
        if retrieved_floor_id != floor_id:
            print(f"    ⚠ floor ID mismatch: esperado {floor_id}, got {retrieved_floor_id}")

        for ae in act_conn["edges"]:
            activities.append(ae["node"])

        pi = act_conn["pageInfo"]
        if not pi["hasNextPage"]:
            break
        act_cursor = pi["endCursor"]

    return activities


def collect_floors_with_cursors(project_id: int):
    """
    Coleta floors COM os edge cursors para uso no collect_activities_via_cursor.
    Retorna lista de dicts com floor data + 'edge_cursor' + 'prev_cursor'.
    """
    floors_with_cursors = []
    cursor = ""
    page = 0
    prev_cursor = ""

    while True:
        page += 1
        after_clause = f', after: "{cursor}"' if cursor else ""

        q = f"""{{ me(id: 479) {{
          project(id: {project_id}) {{
            floorsPage(first: {PAGE_SIZE_FLOORS}{after_clause}) {{
              totalCount
              pageInfo {{ hasNextPage endCursor }}
              edges {{
                cursor
                node {{
                  id name position tag startAt endAt
                  hasQualityLocalsAssociations
                  activitiesPage {{ totalCount }}
                }}
              }}
            }}
          }}
        }}}}"""

        body = fetch_with_retry(q, TIMEOUT_FLOORS, f"floors+cursors p{page}")
        if not body:
            print(f"  ✗ Falhou floors p{page}")
            break

        conn = body["data"]["me"]["project"]["floorsPage"]
        for edge in conn["edges"]:
            floor_data = edge["node"]
            floor_data["edge_cursor"] = edge["cursor"]
            floor_data["prev_cursor"] = prev_cursor
            floors_with_cursors.append(floor_data)
            prev_cursor = edge["cursor"]

        total = conn["totalCount"]
        print(f"  floors+cursors: {len(floors_with_cursors)}/{total} (p{page})")

        pi = conn["pageInfo"]
        if not pi["hasNextPage"]:
            break
        cursor = pi["endCursor"]

    return floors_with_cursors


# ─── coleta principal ─────────────────────────────────────────────────────────

def collect_project(project_id: int, project_name: str) -> dict:
    """Coleta todos os floors + activities do projeto. Retorna summary."""
    print(f"\n{'═'*65}")
    print(f"  {project_name} ({project_id})")
    print(f"{'═'*65}")

    # Checkpoint: se já existe arquivo parcial, carrega
    checkpoint_file = DATA_DIR / f"{project_id}_activities_checkpoint.json"
    out_file        = DATA_DIR / f"{project_id}_activities_raw.json"

    checkpoint = {}
    if checkpoint_file.exists():
        try:
            checkpoint = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            print(f"  ↺ Checkpoint encontrado: {len(checkpoint.get('floors_done', {}))} floors completos")
        except Exception:
            checkpoint = {}

    floors_done: dict[str, list] = checkpoint.get("floors_done", {})

    # Etapa 1: coletar floors com cursors
    print(f"\n  [1/2] Coletando floors...")
    floors = collect_floors_with_cursors(project_id)
    if not floors:
        print("  ✗ Nenhum floor coletado — abortando")
        return {}

    print(f"  ✓ {len(floors)} floors coletados")

    # Etapa 2: coletar activities por floor
    print(f"\n  [2/2] Coletando activities por floor...")
    total_activities = 0
    total_skipped    = 0
    errors           = []

    for i, floor in enumerate(floors):
        fid   = floor["id"]
        fname = floor.get("name", "?")
        expected = floor["activitiesPage"]["totalCount"]

        if fid in floors_done:
            total_activities += len(floors_done[fid])
            total_skipped += 1
            print(f"  [{i+1:3d}/{len(floors)}] ↺ {fname[:40]} — {len(floors_done[fid])} acts (cached)")
            continue

        if expected == 0:
            floors_done[fid] = []
            print(f"  [{i+1:3d}/{len(floors)}] ∅ {fname[:40]} — 0 activities")
            # salva checkpoint
            checkpoint_file.write_text(
                json.dumps({"floors_done": floors_done, "floors": floors}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            continue

        print(f"  [{i+1:3d}/{len(floors)}] {fname[:40]} — esperadas: {expected} acts", end="", flush=True)

        acts = collect_activities_via_cursor(
            project_id=project_id,
            floor_prev_cursor=floor["prev_cursor"],
            floor_id=fid,
            total_activities=expected,
        )

        floors_done[fid] = acts
        total_activities += len(acts)

        status = "✓" if len(acts) >= expected else f"⚠ ({len(acts)}/{expected})"
        print(f" → {status} {len(acts)} coletadas")

        if len(acts) < expected and expected > 0:
            errors.append({"floor_id": fid, "floor_name": fname, "expected": expected, "got": len(acts)})

        # salva checkpoint após cada floor
        checkpoint_file.write_text(
            json.dumps({"floors_done": floors_done, "floors": floors}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # Flatten: lista global de activities
    all_activities = []
    for floor in floors:
        fid = floor["id"]
        for act in floors_done.get(fid, []):
            act["_floor_name"] = floor.get("name", "")
            act["_floor_position"] = floor.get("position")
            act["_floor_tag"] = floor.get("tag")
            act["_floor_start_at"] = floor.get("startAt")
            act["_floor_end_at"] = floor.get("endAt")
            act["_floor_has_quality"] = floor.get("hasQualityLocalsAssociations")
            all_activities.append(act)

    # Salva resultado final
    result = {
        "project_id": project_id,
        "project_name": project_name,
        "collected_at": datetime.now().isoformat(),
        "floors_total": len(floors),
        "activities_total": total_activities,
        "activities_list": all_activities,
        "floors": floors,
        "errors": errors,
    }
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if checkpoint_file.exists():
        checkpoint_file.unlink()  # limpa checkpoint

    print(f"\n  ✓ CONCLUÍDO: {len(floors)} floors, {total_activities} activities")
    if errors:
        print(f"  ⚠ {len(errors)} floors com menos activities do que o esperado:")
        for e in errors[:5]:
            print(f"      {e['floor_name']}: got {e['got']}/{e['expected']}")
    print(f"  Salvo: {out_file}")
    return result


# ─── análise cruzada ──────────────────────────────────────────────────────────

def build_cross_analysis(results: list[dict]):
    """Gera análise cruzada Activities × QualityAssociations."""
    output = {}

    for r in results:
        pid = r["project_id"]
        acts = r["activities_list"]

        # Carrega QualityAssociations já coletadas em Fase 2
        qa_file = DATA_DIR / f"{pid}_qa_raw.json"
        qa_data = []
        if qa_file.exists():
            try:
                raw = json.loads(qa_file.read_text(encoding="utf-8"))
                # formato: lista de QAs ou dict com 'quality_associations'
                if isinstance(raw, list):
                    qa_data = raw
                elif isinstance(raw, dict):
                    qa_data = raw.get("quality_associations", raw.get("qualityAssociations", []))
            except Exception:
                pass

        # Índice: activityId → QAs
        qa_by_item: dict[str, list] = {}
        for qa in qa_data:
            item_id = str(qa.get("itemId", ""))
            if item_id:
                qa_by_item.setdefault(item_id, []).append(qa)

        # Métricas
        total = len(acts)
        with_quality = sum(1 for a in acts if a.get("hasQualityAssociations"))
        without_quality = total - with_quality

        # Atividades maduras (≥80% concluídas) sem cobertura de qualidade
        mature_no_quality = [
            a for a in acts
            if (a.get("percentageCompleted") or 0) >= 80
            and not a.get("hasQualityAssociations")
        ]

        # Atividades 100% concluídas sem qualidade
        done_no_quality = [
            a for a in acts
            if (a.get("percentageCompleted") or 0) >= 100
            and not a.get("hasQualityAssociations")
        ]

        # Progresso médio com/sem qualidade
        acts_with_q   = [a for a in acts if a.get("hasQualityAssociations")]
        acts_without_q = [a for a in acts if not a.get("hasQualityAssociations")]
        avg_with    = sum(a.get("percentageCompleted") or 0 for a in acts_with_q)    / max(len(acts_with_q), 1)
        avg_without = sum(a.get("percentageCompleted") or 0 for a in acts_without_q) / max(len(acts_without_q), 1)

        # Por floor: cobertura
        floors_summary = {}
        for a in acts:
            fid = a.get("floorId") or a.get("_floor_position", "?")
            fn  = a.get("_floor_name", a.get("floorNameWithActivityPart", "?"))
            if fid not in floors_summary:
                floors_summary[fid] = {
                    "floor_name": fn,
                    "total": 0, "with_quality": 0,
                    "avg_progress": 0.0, "sum_progress": 0.0,
                    "mature_no_quality": 0,
                }
            fs = floors_summary[fid]
            fs["total"] += 1
            if a.get("hasQualityAssociations"):
                fs["with_quality"] += 1
            prog = a.get("percentageCompleted") or 0
            fs["sum_progress"] += prog
            if prog >= 80 and not a.get("hasQualityAssociations"):
                fs["mature_no_quality"] += 1

        for fs in floors_summary.values():
            fs["avg_progress"] = round(fs["sum_progress"] / max(fs["total"], 1), 1)
            del fs["sum_progress"]

        output[str(pid)] = {
            "project_name": r["project_name"],
            "activities_total": total,
            "with_quality": with_quality,
            "without_quality": without_quality,
            "coverage_pct": round(with_quality / max(total, 1) * 100, 2),
            "avg_progress_with_quality": round(avg_with, 2),
            "avg_progress_without_quality": round(avg_without, 2),
            "mature_no_quality_count": len(mature_no_quality),
            "done_no_quality_count": len(done_no_quality),
            "mature_no_quality_sample": mature_no_quality[:10],
            "qa_total": len(qa_data),
            "qa_unique_activities": len(qa_by_item),
            "floors_summary": floors_summary,
        }

    return output


# ─── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("  FASE 3 — Coleta de Activities")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    results = []
    for proj in PROJECTS:
        r = collect_project(proj["id"], proj["name"])
        if r:
            results.append(r)

    if results:
        print(f"\n{'═'*65}")
        print("  ANÁLISE CRUZADA Activities × QualityAssociations")
        print(f"{'═'*65}")
        analysis = build_cross_analysis(results)

        for pid, metrics in analysis.items():
            print(f"\n  {metrics['project_name']} ({pid})")
            print(f"    Activities total:       {metrics['activities_total']}")
            print(f"    Com qualidade:          {metrics['with_quality']} ({metrics['coverage_pct']}%)")
            print(f"    Sem qualidade:          {metrics['without_quality']}")
            print(f"    Progresso médio (com):  {metrics['avg_progress_with_quality']}%")
            print(f"    Progresso médio (sem):  {metrics['avg_progress_without_quality']}%")
            print(f"    Maduras sem qualidade:  {metrics['mature_no_quality_count']} (≥80%)")
            print(f"    Concluídas sem quality: {metrics['done_no_quality_count']} (=100%)")
            print(f"    QAs mapeadas:           {metrics['qa_total']} ({metrics['qa_unique_activities']} activities únicas)")

        analysis_file = Path("data") / "FASE3_ACTIVITIES_ANALYSIS.json"
        analysis_file.write_text(
            json.dumps({
                "generated_at": datetime.now().isoformat(),
                "projects": analysis
            }, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n  Análise salva: {analysis_file}")

    print(f"\n{'═'*65}")
    print("  CONCLUÍDO")
    print(f"{'═'*65}")
