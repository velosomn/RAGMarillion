import pytest

from src.chunking import chunk_pages, clean_page, find_headings, split_paragraphs
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


def test_heading_glued_to_text_is_detected():
    # pypdf costuma extrair sem linha em branco entre o título e o texto
    body = "\n".join(f"linha {i} do texto" for i in range(30))
    pages = [(1, f"Capítulo 1\n{body}"), (2, f"Capítulo 2\n{body}")]
    chunks = chunk_pages(pages, chunk_size_words=80, overlap_words=10, chapter_regex=r"^Capítulo \d+")
    assert {c.chapter for c in chunks} == {"Capítulo 1", "Capítulo 2"}
    assert find_headings(pages, r"^Capítulo \d+") == [
        {"page": 1, "title": "Capítulo 1", "repeat": False},
        {"page": 2, "title": "Capítulo 2", "repeat": False},
    ]


def test_running_header_with_chapter_name_is_ignored():
    body = " ".join(f"w{i}" for i in range(50))
    pages = [(1, f"Capítulo 1\n\n{body}"), (2, f"CAPÍTULO 1\n{body}")]
    chunks = chunk_pages(pages, chunk_size_words=500, overlap_words=10, chapter_regex=r"(?i)^capítulo \d+")
    assert len(chunks) == 1  # o cabeçalho da página 2 não corta o capítulo
    assert chunks[0].n_words == 100
    assert [h["repeat"] for h in find_headings(pages, r"(?i)^capítulo \d+")] == [False, True]


def test_no_overlap_only_chunk_at_chapter_end():
    # capítulo termina exatamente no limite do chunk: o buffer só com overlap não vira chunk
    body = " ".join(f"w{i}" for i in range(80))
    pages = [(1, f"Capítulo 1\n\n{body}\n\nCapítulo 2\n\n{body}")]
    chunks = chunk_pages(pages, chunk_size_words=80, overlap_words=10, chapter_regex=r"^Capítulo \d+")
    assert [(c.chapter, c.n_words) for c in chunks] == [("Capítulo 1", 80), ("Capítulo 2", 80)]


def test_clean_page_normalizes_accents():
    decomposed = "Fëanor"
    assert clean_page(decomposed) == "Fëanor"


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
