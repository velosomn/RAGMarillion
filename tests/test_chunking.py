import pytest

from src.chunking import chunk_pages, clean_page, split_paragraphs
from src.retrieval import hit_at_k, reciprocal_rank, parse_search_result


def test_clean_page_drops_page_numbers_and_fixes_hyphens():
    raw = "42\nA Montanha Soli-\ntária\n"
    assert clean_page(raw) == "A Montanha Solitária"


def test_split_paragraphs_joins_lines():
    assert split_paragraphs("linha um\nlinha dois\n\noutro") == ["linha um linha dois", "outro"]


def _pages():
    body = " ".join(f"w{i}" for i in range(100))
    return [
        (1, f"Capítulo 1\n\n{body}"),
        (2, f"{body}\n\nCapítulo 2\n\n{body}"),
    ]


def test_chunks_never_cross_chapters():
    chunks = chunk_pages(_pages(), chunk_size_words=80, overlap_words=10, chapter_regex=r"^Capítulo \d+")
    chapters = {c.chapter for c in chunks}
    assert chapters == {"Capítulo 1", "Capítulo 2"}
    # capítulo 2 começa limpo, sem overlap vindo do capítulo 1
    first_ch2 = next(c for c in chunks if c.chapter == "Capítulo 2")
    assert first_ch2.chunk_index == 0
    assert first_ch2.page_start == 2


def test_overlap_and_size():
    chunks = chunk_pages(_pages(), chunk_size_words=80, overlap_words=10, chapter_regex=r"^Capítulo \d+",
                         prepend_chapter=False)
    assert all(c.n_words <= 80 for c in chunks)
    c0, c1 = chunks[0], chunks[1]
    assert c0.text.split()[-10:] == c1.text.split()[:10]


def test_prepend_chapter():
    chunks = chunk_pages(_pages(), chunk_size_words=80, overlap_words=0, chapter_regex=r"^Capítulo \d+")
    assert chunks[0].text.startswith("[Capítulo 1] ")


def test_unique_ids():
    chunks = chunk_pages(_pages(), chunk_size_words=30, overlap_words=5)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_overlap_must_be_smaller():
    with pytest.raises(ValueError):
        chunk_pages(_pages(), chunk_size_words=10, overlap_words=10)


def test_retrieval_metrics():
    hits = [{"text": "nada aqui"}, {"text": "Fëanor fez as joias"}]
    assert hit_at_k(hits, ["fëanor"])
    assert reciprocal_rank(hits, ["Fëanor"]) == 0.5
    assert not hit_at_k(hits, [])


def test_parse_search_result():
    res = {
        "manifest": {"columns": [{"name": "chunk_id"}, {"name": "text"}, {"name": "score"}]},
        "result": {"data_array": [["c00001", "abc", 0.9]]},
    }
    assert parse_search_result(res) == [{"chunk_id": "c00001", "text": "abc", "score": 0.9}]
    assert parse_search_result({"manifest": {"columns": []}, "result": {}}) == []
