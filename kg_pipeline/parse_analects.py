from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple


WORK_NAME = "Analects"

# --------- 정규식들 ---------
# <學而第一>01  또는  <爲政第二> 24  ... 같은 케이스 지원
RE_CHAPTER_NUM = re.compile(
    r"""^\s*<(?P<chapter>[^>]+)>\s*(?P<num>\d{1,3})\s*(?P<rest>.*)\s*$"""
)

# <八佾第三> 처럼 "편만" 나오는 헤더 줄 (설명/주석 뒤에 절들이 이어지는 경우)
RE_CHAPTER_ONLY = re.compile(r"^\s*<(?P<inside>[^>]+)>\s*$")

# 한문 발화자 패턴 (최대한 안전하게)
# 예: 子曰, ... / 有子曰, ... / 曾子曰, ... / 子貢曰, ... / 哀公問曰, ...
# speaker는 "子", "有子", "曾子", "子貢", "哀公" 등으로 잡힘(최대 12자 제한)
RE_SPEAKER = re.compile(
    r"""^\s*(?P<speaker>.{1,12}?)(?:曰|問曰|對曰)\s*[，,]\s*(?P<body>.+?)\s*$"""
)

RE_SPACES = re.compile(r"\s+")

# 챕터 헤더(한문/한자) 엄격 판별:
#  - 한글이 없어야 함
#  - 문자열 끝이 "...第八" / "...第8" / "...第一" 같은 형태여야 함
RE_CHAPTER_STRICT = re.compile(
    r"""^.{1,40}?第\s*(\d+|[一二三四五六七八九十百千]+)\s*$"""
)


@dataclass
class Passage:
    work: str
    chapter: str
    number: int
    passage_id: str
    text_zh: str
    text_ko: str
    speaker: Optional[str] = None


def normalize_spaces(s: str) -> str:
    s = s.strip()
    s = RE_SPACES.sub(" ", s)
    s = s.replace(" ,", ",").replace(" ，", "，")
    return s.strip()


def clean_line(line: str) -> str:
    return line.strip().replace("\u3000", " ")


def is_likely_ko(line: str) -> bool:
    """한글 포함 여부로 대략적인 한국어 라인 판단."""
    return bool(re.search(r"[가-힣]", line))


def is_chapter_header(text_inside_brackets: str) -> bool:
    """
    <...> 안의 텍스트가 진짜 '편 제목'인지 엄격 판별

    - 한글이 하나라도 있으면 설명/번역으로 간주 -> False
    - 길이가 너무 길면 설명일 확률이 높음 -> False
    - 끝이 "...第N" 형태로 끝나는 경우만 True
      예: 學而第一 / 爲政第二 / 八佾第三 / 泰伯第八 / 子罕第九 ...
    """
    t = normalize_spaces(text_inside_brackets)

    if re.search(r"[가-힣]", t):
        return False
    if len(t) > 40:
        return False

    return bool(RE_CHAPTER_STRICT.match(t))


def extract_speaker_and_body(zh_text: str) -> Tuple[Optional[str], str]:
    """
    한문 텍스트 첫머리에서 speaker를 추출하고,
    추출되면 "子曰," 같은 프리픽스를 제거한 본문만 반환.
    """
    m = RE_SPEAKER.match(zh_text)
    if not m:
        return None, zh_text
    speaker = normalize_spaces(m.group("speaker"))
    body = normalize_spaces(m.group("body"))
    if len(speaker) > 12:
        return None, zh_text
    return speaker, body


def finalize_passage(chapter: str, number: int, zh_lines: List[str], ko_lines: List[str]) -> Passage:
    zh = normalize_spaces(" ".join([clean_line(x) for x in zh_lines if clean_line(x)]))
    ko = normalize_spaces(" ".join([clean_line(x) for x in ko_lines if clean_line(x)]))

    speaker, zh_body = extract_speaker_and_body(zh)
    passage_id = f"{chapter}_{number:02d}"

    return Passage(
        work=WORK_NAME,
        chapter=chapter,
        number=number,
        passage_id=passage_id,
        text_zh=zh_body,
        text_ko=ko,
        speaker=speaker,
    )


def parse_analects_text(text: str) -> List[Passage]:
    """
    입력 텍스트에서 Passage 리스트를 생성.

    주요 가정:
    - "<學而第一>01" 형태가 절의 시작을 알려준다(최우선).
    - "<八佾第三>" 같이 '편만' 나오는 헤더가 있을 수 있다.
    - 편 헤더 직후 "<...>" 한 줄이 더 나오면 '편 설명'으로 간주하고 무시한다.
    - 절의 한문/한글은 여러 줄로 나뉘어 있어도 이어붙인다.
    """
    lines = text.splitlines()

    current_chapter: Optional[str] = None
    current_number: Optional[int] = None
    zh_buf: List[str] = []
    ko_buf: List[str] = []
    passages: List[Passage] = []

    # 편 헤더 직후 "<...>" 한 줄을 설명으로 먹을지 여부
    expecting_chapter_desc = False

    def flush_if_ready():
        nonlocal current_chapter, current_number, zh_buf, ko_buf, passages
        if current_chapter is None or current_number is None:
            return
        if not zh_buf and not ko_buf:
            return
        passages.append(finalize_passage(current_chapter, current_number, zh_buf, ko_buf))
        zh_buf = []
        ko_buf = []

    for raw in lines:
        line = clean_line(raw)
        if not line:
            continue

        # 1) 절 시작: <chapter>nn
        m = RE_CHAPTER_NUM.match(line)
        if m:
            flush_if_ready()

            current_chapter = normalize_spaces(m.group("chapter"))
            current_number = int(m.group("num"))
            rest = clean_line(m.group("rest"))

            zh_buf = []
            ko_buf = []

            expecting_chapter_desc = False  # 절 시작이면 해제

            if rest:
                if is_likely_ko(rest):
                    ko_buf.append(rest)
                else:
                    zh_buf.append(rest)
            continue

        # 2) <...> 단독 줄 처리 (편 헤더 / 편 설명 / 본문 중 괄호라인)
        m2 = RE_CHAPTER_ONLY.match(line)
        if m2:
            inside = normalize_spaces(m2.group("inside"))

            # (A) 진짜 편 헤더면 chapter 갱신
            if is_chapter_header(inside):
                current_chapter = inside
                expecting_chapter_desc = True
                continue

            # (B) 편 헤더 직후의 <...>는 설명으로 간주하고 무시
            if expecting_chapter_desc:
                expecting_chapter_desc = False
                continue

            # (C) 그 외 <...> 라인은 본문일 수 있으니 절 시작된 상태면 버퍼에 누적
            if current_chapter is not None and current_number is not None:
                if is_likely_ko(line):
                    ko_buf.append(line)
                else:
                    zh_buf.append(line)
            continue

        # 3) 절이 아직 시작되지 않았다면 무시 (파일 앞의 안내문 등)
        if current_chapter is None or current_number is None:
            expecting_chapter_desc = False
            continue

        # 4) 본문 누적: 한글 포함이면 ko, 아니면 zh
        if is_likely_ko(line):
            ko_buf.append(line)
        else:
            zh_buf.append(line)

        expecting_chapter_desc = False

    flush_if_ready()
    return passages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True, help="Input text file (analects_of_confucius.txt)")
    ap.add_argument("--output", "-o", required=True, help="Output JSON file (analects_passages.json)")
    ap.add_argument("--ensure-ascii", action="store_true", help="Escape non-ASCII chars in JSON (default: keep unicode)")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    text = in_path.read_text(encoding="utf-8", errors="ignore")
    passages = parse_analects_text(text)

    payload = [asdict(p) for p in passages]

    out_path.write_text(
        json.dumps(payload, ensure_ascii=args.ensure_ascii, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Parsed passages: {len(payload)}")
    if payload:
        print("[Sample]")
        print(json.dumps(payload[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
