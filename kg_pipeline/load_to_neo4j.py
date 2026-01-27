# load_to_neo4j.py
# ------------------------------------------------------------
# analects_passages.json -> Neo4j
# 추가 관계:
#  - (Passage)-[:NEXT]->(Passage)          # same chapter ordering
#  - (Passage)-[:SPOKEN_BY]->(Speaker)     # if speaker exists
#  - (Passage)-[:MENTIONS]->(Concept)      # keyword mentions (zh/ko)
# ------------------------------------------------------------

import json
import argparse
from pathlib import Path
from collections import defaultdict
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


WORK_NAME = "Analects"

# 개념 키워드 (원하면 더 추가 가능)
CONCEPT_KEYWORDS = [
    ("仁", ["仁", "인"]),
    ("義", ["義", "의"]),
    ("禮", ["禮", "예"]),
    ("孝", ["孝", "효"]),
    ("君子", ["君子", "군자"]),
    ("小人", ["小人", "소인"]),
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def detect_concepts(text_zh: str, text_ko: str):
    hits = []
    zh = text_zh or ""
    ko = text_ko or ""
    for concept, toks in CONCEPT_KEYWORDS:
        if any(t in zh for t in toks) or any(t in ko for t in toks):
            hits.append(concept)
    return hits


def load_to_neo4j(uri, user, password, passages):
    driver = GraphDatabase.driver(uri, auth=(user, password))

    # chapter별로 passage_id 정렬해 NEXT 연결 만들기 위해 미리 모음
    by_chapter = defaultdict(list)

    with driver.session() as session:
        # (선택) 유니크 제약/인덱스: 처음 1번만 실행하면 됨
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (w:Work) REQUIRE w.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chapter) REQUIRE c.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Passage) REQUIRE p.passage_id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Speaker) REQUIRE s.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (k:Concept) REQUIRE k.name IS UNIQUE")

        # 1) Work
        session.run("MERGE (w:Work {name:$name})", name=WORK_NAME)

        # 2) Chapter / Passage / Speaker / Concept 로드
        for p in passages:
            work = p.get("work") or WORK_NAME
            chapter = p["chapter"]
            pid = p["passage_id"]
            number = int(p["number"])
            text_zh = p.get("text_zh", "")
            text_ko = p.get("text_ko", "")
            speaker = p.get("speaker")

            by_chapter[chapter].append((number, pid))

            session.run(
                """
                MATCH (w:Work {name:$work})
                MERGE (c:Chapter {name:$chapter})
                MERGE (w)-[:HAS_CHAPTER]->(c)

                MERGE (ps:Passage {passage_id:$pid})
                SET ps.number=$number, ps.text_zh=$text_zh, ps.text_ko=$text_ko

                MERGE (c)-[:HAS_PASSAGE]->(ps)
                """,
                work=work, chapter=chapter, pid=pid,
                number=number, text_zh=text_zh, text_ko=text_ko
            )

            # 2-1) Speaker 관계
            if speaker:
                session.run(
                    """
                    MATCH (ps:Passage {passage_id:$pid})
                    MERGE (sp:Speaker {name:$speaker})
                    MERGE (ps)-[:SPOKEN_BY]->(sp)
                    """,
                    pid=pid, speaker=speaker
                )

            # 2-2) Concept 관계
            concepts = detect_concepts(text_zh, text_ko)
            if concepts:
                session.run(
                    """
                    MATCH (ps:Passage {passage_id:$pid})
                    UNWIND $concepts AS cname
                    MERGE (k:Concept {name:cname})
                    MERGE (ps)-[:MENTIONS]->(k)
                    """,
                    pid=pid, concepts=concepts
                )

        # 3) NEXT 관계: 같은 chapter 내 number 순서대로 연결
        for chapter, items in by_chapter.items():
            items.sort(key=lambda x: x[0])  # number 기준 정렬
            for (n1, pid1), (n2, pid2) in zip(items, items[1:]):
                session.run(
                    """
                    MATCH (a:Passage {passage_id:$pid1})
                    MATCH (b:Passage {passage_id:$pid2})
                    MERGE (a)-[:NEXT]->(b)
                    """,
                    pid1=pid1, pid2=pid2
                )

    driver.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True, help="analects_passages.json")
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--user", default="neo4j")
    ap.add_argument("--password", required=True)
    args = ap.parse_args()

    import os
    # .env에서 load_dotenv()가 이미 위에서 실행된 상황에서
    if not args.uri:
        args.uri = os.environ.get("NEO4J_URI")
    if not args.user:
        args.user = os.environ.get("NEO4J_USER", "neo4j")
    if not args.password:
        args.password = os.environ.get("NEO4J_PASSWORD")

    if not args.uri:
        raise ValueError("NEO4J_URI가 비어 있습니다. .env 또는 환경변수를 확인하세요.")
    if not args.password:
        raise ValueError("NEO4J_PASSWORD가 비어 있습니다. .env 또는 환경변수를 확인하세요.")

    passages = load_json(Path(args.input))
    load_to_neo4j(args.uri, args.user, args.password, passages)
    print(f"[OK] Loaded passages: {len(passages)}")


if __name__ == "__main__":
    main()
