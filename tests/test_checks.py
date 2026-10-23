import json
import re
from pathlib import Path

import pytest

from src import checks
from src.chunking import chunk_pages, clean_page, find_headings

REGEX = r"^Capítulo \d+"


def _book(n_pages=10, header=None):
    body = "\n".join(f"Fëanor e Morgoth linha {i}" for i in range(20))
    pages = []
    for n in range(1, n_pages + 1):
        title = f"Capítulo {n // 3 + 1}\n" if n % 3 == 0 else ""
        top = f"{header} {n}\n" if header else ""
        pages.append((n, f"{top}{title}{body}"))
    return pages


def test_report_raises_only_on_error():
    rep = checks.Report("x")
    rep.add("aviso", checks.Result(False, "d"), level="AVISO")
    rep.finish()  # AVISO não para
    rep.add("erro", checks.Result(False, "d"))
    with pytest.raises(RuntimeError):
        rep.finish()


def test_empty_pages():
    pages = [(1, "texto"), (2, ""), (3, "  "), (4, "texto")]
    assert checks.empty_pages(pages, 0.6).ok
    assert not checks.empty_pages(pages, 0.4).ok


def test_anchor_terms_ignore_case_and_accent_encoding():
    pages = [(1, "FËANOR forjou")]  # acento decomposto
    assert checks.anchor_terms(pages, ["Fëanor", "Gondolin"], 0.5).ok
    assert not checks.anchor_terms(pages, ["Fëanor", "Gondolin"], 0.75).ok


def test_bad_chars_detects_broken_diacritics():
    res = checks.bad_chars([(1, "F¨eanor e ﬁlhos")], 0.0)
    assert not res.ok and "F¨eanor" in res.detail
    assert checks.bad_chars([(1, "Fëanor e filhos")], 0.0).ok


def test_repeated_lines_suggests_pattern_that_drops_the_header():
    letters = "abcdefghij"
    raw = [(n, f"O  SILMARILLION {n}\n" + "\n".join(f"{letters[n - 1] * k} texto" for k in range(1, 6)))
           for n in range(1, 11)]
    pages = [(n, clean_page(t)) for n, t in raw]
    res = checks.repeated_lines(pages, 0.2)
    assert not res.ok
    pattern = re.search(r'r"(.+)"', res.detail).group(1)
    cleaned = [(n, clean_page(t, [r"^\s*\d{1,4}\s*$", pattern])) for n, t in raw]
    assert checks.repeated_lines(cleaned, 0.2).ok


def test_chapter_count_and_duplicates():
    pages = _book(n_pages=9)
    headings = find_headings(pages, REGEX)
    assert checks.chapter_count(headings, (3, 3)).ok
    assert not checks.chapter_count(headings, (5, 10)).ok
    assert checks.duplicate_headings(headings).ok

    alternating = pages + [(10, "Capítulo 2\ntexto")]  # título reaparece depois de outro capítulo
    assert not checks.duplicate_headings(find_headings(alternating, REGEX)).ok


def test_long_heading_lines():
    pages = [(1, "Capítulo 1 " + " ".join(["palavra"] * 20))]
    assert not checks.long_heading_lines(pages, REGEX).ok
    assert checks.long_heading_lines([(1, "Capítulo 1\ntexto")], REGEX).ok


def test_chapter_distribution_checks():
    chunks = chunk_pages(_book(n_pages=9), chunk_size_words=40, overlap_words=5, chapter_regex=REGEX)
    assert checks.small_chapters(chunks, 2).ok
    assert not checks.small_chapters(chunks, 100).ok
    assert checks.dominant_chapter(chunks, 0.5).ok
    assert not checks.dominant_chapter(chunks, 0.1).ok
    assert checks.short_chunks(chunks, 10, 0.0).ok


def test_word_coverage_is_exact_for_chunk_pages():
    pages = _book(n_pages=9)
    for overlap in (0, 5, 30):
        chunks = chunk_pages(pages, chunk_size_words=40, overlap_words=overlap, chapter_regex=REGEX)
        res = checks.word_coverage(pages, chunks, REGEX, overlap, 0.0)
        assert res.ok, res.detail
    assert not checks.word_coverage(pages, chunks[:-1], REGEX, 30, 0.0).ok


def test_index_checks():
    assert checks.index_rows(10, 10).ok
    assert not checks.index_rows(None, 10).ok
    assert checks.self_retrieval([("c1", ["c1"]), ("c2", ["c9"])]).ok
    assert not checks.self_retrieval([("c1", ["c9"]), ("c2", ["c9"]), ("c3", ["c3"])]).ok
    assert not checks.self_retrieval([]).ok


def test_citations():
    refusal = "Não encontrei isso nos trechos recuperados"
    assert checks.citations("Fëanor [c00001].", ["c00001"], refusal).ok
    assert checks.citations("Fëanor [c00001, c00002].", ["c00001", "c00002"], refusal).ok
    assert not checks.citations("Fëanor [c00007].", ["c00001"], refusal).ok
    assert not checks.citations("Fëanor.", ["c00001"], refusal).ok
    assert checks.citations(refusal + ".", [], refusal).ok


def test_validate_eval_set():
    good = {"id": "q1", "category": "factual", "question": "?", "expected_response": "x", "expected_terms": ["x"]}
    assert checks.validate_eval_set([good]).ok
    assert not checks.validate_eval_set([good, good]).ok  # id repetido
    assert not checks.validate_eval_set([{**good, "category": "outra"}]).ok
    assert not checks.validate_eval_set([{**good, "expected_terms": []}]).ok
    assert not checks.validate_eval_set([{"id": "q1"}]).ok


def test_shipped_eval_set_is_valid():
    path = Path(__file__).parent.parent / "data" / "eval_questions.jsonl"
    eval_set = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    res = checks.validate_eval_set(eval_set)
    assert res.ok, res.detail


def test_expected_terms_in_corpus():
    eval_set = [
        {"id": "q1", "category": "factual", "expected_terms": ["Fëanor", "Silmarilli"]},
        {"id": "q2", "category": "factual", "expected_terms": ["Gondolin"]},
        {"id": "q3", "category": "unanswerable", "expected_terms": []},
    ]
    missing = checks.missing_terms(eval_set, ["FËANOR forjou as Silmarils"])
    assert missing == {"q1": ["Silmarilli"], "q2": ["Gondolin"]}
    assert checks.unreachable_questions(eval_set, missing) == ["q2"]
    assert not checks.absent_terms(missing).ok
