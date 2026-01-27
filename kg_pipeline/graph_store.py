# graph_store.py
import os, sys, time
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv

CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# .env 파일 로드 (절대 경로 지정으로 어디서든 실행 가능)
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    print(f"Warning: .env file not found at {ENV_PATH}")

def get_neo4j_driver():
    # Neo4j 드라이버 인스턴스를 생성하여 반환한다.
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")

    print(f"[DEBUG][neo4j] URI={uri} USER={user} PWD={'SET' if password else 'MISSING'}",
file=sys.stderr, flush=True)

    if not all([uri, user, password]):
        raise ValueError("Neo4j 환경 변수가 누락되었습니다. .env 파일을 확인하세요.")
        
    return GraphDatabase.driver(uri, auth=(user, password))

def test_neo4j_connection():
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:

            result = session.run("MATCH (c:Concept) RETURN c.name AS name LIMIT 5")
            return [r["name"] for r in result]
    finally:
        driver.close()


def extract_concepts_mvp(question: str) -> list[str]:
    q = question.strip()

    # 1) 기본 매핑(한글/한자 키워드 → Concept name)
    mapping = {
        # core
        "인": "仁", "仁": "仁",
        "의": "義", "義": "義",
        "예": "禮", "禮": "禮",
        "효": "孝", "孝": "孝",
        "군자": "君子", "君子": "君子",
        "소인": "小人", "小人": "小人",

        # governance / social order
        "정치": "政", "政": "政",
        "다스림": "治", "치": "治", "治": "治",
        "나라": "國", "국가": "國", "國": "國",
        "가정": "家", "집": "家", "家": "家",
        "백성": "民", "민": "民", "民": "民",
        "임금": "君", "군": "君", "君": "君",
        "신하": "臣", "臣": "臣",
    }

    hits = []
    for k, v in mapping.items():
        if k in q:
            hits.append(v)

    # 2) 질문 패턴 보정: "개인 vs 사회/질서" 류면 사회축을 자동으로 보강
    if ("효" in q or "孝" in q) and any(t in q for t in ["사회", "질서", "정치", "국가", "나라"]):
        hits += ["政", "國", "民", "君", "家"]

    # dedup (순서 유지)
    deduped = []
    seen = set()
    for x in hits:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped

def retrieve_passages_by_concepts(concepts: list[str], k: int = 5) -> list[dict]:
    query = """
    MATCH (p:Passage)-[:MENTIONS]->(c:Concept)
    WHERE c.name IN $concepts
    WITH p, collect(DISTINCT c.name) AS hit_concepts, size(collect(DISTINCT c.name)) AS score
    OPTIONAL MATCH (w:Work)-[:HAS_CHAPTER]->(ch:Chapter)-[:HAS_PASSAGE]->(p)
    RETURN score, hit_concepts,
           p.passage_id AS pid,
           ch.number AS chapter_no, ch.name AS chapter,
           p.text_zh AS zh, p.text_ko AS ko
    ORDER BY score DESC, chapter_no, pid
    LIMIT $k
    """

    # 드라이버 생성 (미리 정의된 get_neo4j_driver()가 있다면 그것을 사용하세요)
    driver = get_neo4j_driver()
    params = {"concepts": concepts, "k": int(k)}

    try:
        with driver.session() as s:
            t0 = time.time()
            print("[DEBUG][passages] cypher:", query.strip()[:300], file=sys.stderr, flush=True)
            print("[DEBUG][passages] params:", params, file=sys.stderr, flush=True)

            data = s.run(query, **params).data()

            dt = (time.time() - t0) * 1000
            print(f"[DEBUG][passages] rows={len(data)} time_ms={dt:.1f}", file=sys.stderr, flush=True)
            if data:
                print("[DEBUG][passages] first_row_keys:", list(data[0].keys()), file=sys.stderr, flush=True)

            return data
    except Exception as e:
        import traceback
        print("[ERROR][passages] failed:", repr(e), file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        return []
    finally:
        driver.close()


def build_graph_evidence_block(rows: list[dict], question: str) -> str:
    if not rows:
        return ""

    lines = []
    lines.append("[GRAPH EVIDENCE - Neo4j]")
    lines.append(f"Question: {question}")
    lines.append("Selection rule: passages that mention many of the requested concepts are ranked higher (score = #hit_concepts).")
    lines.append("")

    for r in rows:
        lines.append(f"- score={r['score']} hit={r['hit_concepts']} | {r['chapter']}({r['chapter_no']}) pid={r['pid']}")
        if r.get("zh"):
            lines.append(f"  〈한문〉 {r['zh']}")
        if r.get("ko"):
            lines.append(f"  〈번역〉 {r['ko']}")
        lines.append("")

    return "\n".join(lines).strip()

def retrieve_paths_2hop(concepts: list[str], k_paths: int = 10, k_seed_passages: int = 20) -> list[dict]:
    """
    Neo4j에서 '논증 사슬' 후보를 2-hop 형태로 추출한다.

    Path 형태(개념적으로):
      p1 --MENTIONS--> seedConcept
      p1 --MENTIONS--> bridgeConcept <--MENTIONS-- p2

    - seedConcept: 질문에서 추출된 concepts 중 하나
    - bridgeConcept: p1과 p2가 공유하는 '연결 개념'
    - 결과는 path 후보 목록(딕셔너리들)
    """
    driver = get_neo4j_driver()

    q = """
    // 1) seed concept을 언급하는 passage(p1)들 후보를 먼저 확보
    MATCH (p1:Passage)-[:MENTIONS]->(seed:Concept)
    WHERE seed.name IN $concepts
    WITH p1, collect(DISTINCT seed.name) AS seed_hits, size(collect(DISTINCT seed.name)) AS seed_score
    ORDER BY seed_score DESC
    LIMIT $k_seed_passages

    // 2) p1이 언급하는 다른 concept(bridge)를 통해 이웃 passage(p2)로 확장
    MATCH (p1)-[:MENTIONS]->(bridge:Concept)<-[:MENTIONS]-(p2:Passage)
    WHERE p2 <> p1

    // 3) p2도 seed concept을 언급하는지(직접 관련성) 확인용으로 한 번 더 매치
    OPTIONAL MATCH (p2)-[:MENTIONS]->(seed2:Concept)
    WHERE seed2.name IN $concepts

    WITH p1, p2,
         seed_hits,
         collect(DISTINCT bridge.name) AS bridges,
         collect(DISTINCT seed2.name) AS p2_seed_hits

    // 4) 너무 범용적인 bridge(예: 子, 人 같은)로 폭발하는 걸 막기 위해
    //    bridge 개수 또는 seed hit 등으로 단순 스코어를 만든다 (정교한 점수화는 다음 단계)
    WITH p1, p2, seed_hits, bridges, p2_seed_hits,
         (size(seed_hits) + size(p2_seed_hits)) AS relevance_score,
         size(bridges) AS bridge_strength

    // 5) Work/Chapter 정보 붙이기 (있으면)
    OPTIONAL MATCH (w1:Work)-[:HAS_CHAPTER]->(ch1:Chapter)-[:HAS_PASSAGE]->(p1)
    OPTIONAL MATCH (w2:Work)-[:HAS_CHAPTER]->(ch2:Chapter)-[:HAS_PASSAGE]->(p2)

    RETURN
        relevance_score,
        bridge_strength,
        seed_hits,
        p2_seed_hits,
        bridges,

        p1.passage_id AS p1_pid,
        ch1.number AS p1_chapter_no,
        ch1.name   AS p1_chapter,
        p1.text_zh AS p1_zh,
        p1.text_ko AS p1_ko,

        p2.passage_id AS p2_pid,
        ch2.number AS p2_chapter_no,
        ch2.name   AS p2_chapter,
        p2.text_zh AS p2_zh,
        p2.text_ko AS p2_ko

    ORDER BY relevance_score DESC, bridge_strength DESC, p1_chapter_no ASC, p1_pid ASC
    LIMIT $k_paths
    """

    params = {
        "concepts": concepts,
        "k_paths": int(k_paths),
        "k_seed_passages": int(k_seed_passages),
    }

    try:
        with driver.session() as s:
            t0 = time.time()
            print("[DEBUG][paths] cypher:", q.strip()[:300], file=sys.stderr, flush=True)
            print("[DEBUG][paths] params:", params, file=sys.stderr, flush=True)

            data = s.run(q, **params).data()

            dt = (time.time() - t0) * 1000
            print(f"[DEBUG][paths] rows={len(data)} time_ms={dt:.1f}", file=sys.stderr, flush=True)
            if data:
                print("[DEBUG][paths] first_row_keys:", list(data[0].keys()), file=sys.stderr, flush=True)

            return data
    except Exception as e:
        import traceback
        print("[ERROR][paths] failed:", repr(e), file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        return []
    finally:
        driver.close()

def build_graph_path_evidence_block(paths: list[dict], question: str, max_paths: int = 5) -> str:
    if not paths:
        return ""

    lines = []
    lines.append("[GRAPH PATH EVIDENCE - Neo4j]")
    lines.append(f"Question: {question}")
    lines.append("Each PATH is a 2-hop chain built via shared bridge concepts.")
    lines.append("Try to build an argument chain from 'personal virtue' to 'social order' using these.")
    lines.append("")

    for i, p in enumerate(paths[:max_paths], 1):
        lines.append(f"## PATH {i} | relevance={p.get('relevance_score')} bridge_strength={p.get('bridge_strength')}")
        lines.append(f"- seed_hits(p1): {p.get('seed_hits')}")
        lines.append(f"- seed_hits(p2): {p.get('p2_seed_hits')}")
        lines.append(f"- bridges(shared concepts): {p.get('bridges')}")
        lines.append(f"- p1: {p.get('p1_chapter')}({p.get('p1_chapter_no')}) pid={p.get('p1_pid')}")
        if p.get("p1_zh"):
            lines.append(f"  〈한문〉 {p['p1_zh']}")
        if p.get("p1_ko"):
            lines.append(f"  〈번역〉 {p['p1_ko']}")
        lines.append(f"- p2: {p.get('p2_chapter')}({p.get('p2_chapter_no')}) pid={p.get('p2_pid')}")
        if p.get("p2_zh"):
            lines.append(f"  〈한문〉 {p['p2_zh']}")
        if p.get("p2_ko"):
            lines.append(f"  〈번역〉 {p['p2_ko']}")
        lines.append("")

    return "\n".join(lines).strip()


if __name__ == "__main__":
    q = "논어에서 孝는 개인의 덕목인가, 사회 질서를 위한 기준인가?"
    concepts = extract_concepts_mvp(q)
    
    rows = retrieve_passages_by_concepts(concepts, k=5)

    graph_ctx = build_graph_evidence_block(rows, q)
    print(graph_ctx[:1500])  # 너무 길면 일부만