from types import SimpleNamespace

from src.answer_format import cited_ids, excerpt, format_sources, page_label


def doc(cid, chapter, start, end=None, text="texto"):
    meta = {"chapter": chapter, "page_start": start, "page_end": end if end is not None else start}
    return SimpleNamespace(id=cid, metadata=meta, page_content=text)


def test_cited_ids_in_order_without_repeats():
    assert cited_ids("Fëanor [c00078]. Depois [c00079], e de novo [c00078].") == ["c00078", "c00079"]
    assert cited_ids("Não encontrei isso nos trechos recuperados.") == []
    assert cited_ids(None) == []


def test_page_label():
    assert page_label({"page_start": 158, "page_end": 158}) == "p. 158"
    assert page_label({"page_start": 158.0, "page_end": 160.0}) == "p. 158–160"
    assert page_label({"page_start": 158}) == "p. 158"


def test_format_sources():
    docs = [doc("c00078", "CAPÍTULO VII: DAS SILMARILS", 158), doc("c00079", "CAPÍTULO VII: DAS SILMARILS", 159, 160)]
    answer = "Fëanor [c00078], em Tirion [c00079]; ver também [c00999]."
    assert format_sources(answer, docs) == [
        "[c00078] CAPÍTULO VII: DAS SILMARILS, p. 158",
        "[c00079] CAPÍTULO VII: DAS SILMARILS, p. 159–160",
        "[c00999] (não estava entre os trechos recuperados)",
    ]


def test_excerpt():
    assert excerpt("[CAPÍTULO VII] Naquela  época\nforam feitas") == "Naquela época foram feitas"
    long = excerpt("[X] " + "palavra " * 100, max_chars=30)
    assert long.endswith("…") and len(long) <= 31
