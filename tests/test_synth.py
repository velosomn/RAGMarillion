from src.retrieval import is_relevant, page_scores
from src.synth import (build_messages, check_generation, has_proper_noun, is_excluded, longest_shared_run,
                       parse_generation, split_for, strip_chapter_prefix)

CHUNK = ("[CAPÍTULO VII: DAS SILMARILS] Fëanor foi para o norte e ergueu uma fortaleza em Formenos, "
         "onde guardou as joias em câmaras de ferro.")


def gen(**kw):
    base = {"pergunta": "Onde Fëanor guardou as joias?", "resposta": "Em Formenos.", "termos": ["Formenos"]}
    return {**base, **kw}


def test_prompt_uses_the_chunk_without_the_chapter_label():
    assert strip_chapter_prefix(CHUNK).startswith("Fëanor foi")
    user = build_messages(CHUNK)[1]["content"]
    assert "Fëanor foi para o norte" in user and "[CAPÍTULO" not in user


def test_parse_generation_handles_code_fences_and_garbage():
    raw = 'Claro!\n```json\n{"pergunta": "P?", "resposta": "R", "termos": ["R"]}\n```'
    assert parse_generation(raw) == {"pergunta": "P?", "resposta": "R", "termos": ["R"]}
    assert parse_generation("sem json aqui") is None
    assert parse_generation("{quebrado") is None
    assert parse_generation("") is None


def test_check_generation_accepts_a_good_item():
    assert check_generation(gen(), CHUNK, max_copy_words=6) is None


def test_check_generation_reasons():
    assert check_generation(None, CHUNK, 6) == "json_invalido"
    assert check_generation(gen(termos=[]), CHUNK, 6) == "campos_faltando"
    assert check_generation(gen(resposta=" "), CHUNK, 6) == "campos_faltando"
    assert check_generation(gen(termos=["Angband"]), CHUNK, 6) == "termo_fora_do_trecho"
    assert check_generation(gen(pergunta="Onde ele guardou as joias?"), CHUNK, 6) == "sem_nome_proprio"
    copy = "Por que Fëanor foi para o norte e ergueu uma fortaleza?"
    assert check_generation(gen(pergunta=copy), CHUNK, 6) == "copia_do_trecho"
    assert check_generation(gen(resposta=" ".join(["palavra"] * 30)), CHUNK, 6) == "resposta_longa"


def test_terms_match_ignoring_case_and_accent_encoding():
    assert check_generation(gen(termos=["formenos", "Fëanor"]), CHUNK, 6) is None


def test_has_proper_noun():
    assert has_proper_noun("Quem forjou as Silmarils?")
    assert has_proper_noun("Fëanor guardou as joias onde?")  # nome como primeira palavra
    assert not has_proper_noun("Quem fez isso depois?")
    assert not has_proper_noun("Onde ele guardou as joias?")


def test_longest_shared_run():
    assert longest_shared_run("a b c d", "x a b c y") == 3
    assert longest_shared_run("nada em comum", "outra frase") == 0


def test_split_is_fixed_and_roughly_one_third_test():
    assert split_for("s001") == split_for("s001")
    splits = [split_for(f"s{i:03d}") for i in range(1, 301)]
    assert 70 <= splits.count("test") <= 130


def test_is_excluded_by_chapter_prefix():
    prefixes = ["GLOSSÁRIO", "APÊNDICE", "Início"]
    assert is_excluded("APÊNDICE ELEMENTOS EM NOMES", prefixes)
    assert is_excluded("glossário", prefixes)
    assert not is_excluded("CAPÍTULO VII: DAS SILMARILS", prefixes)


def test_page_scores():
    evidence = [158]
    hits = [(150, 152), (157, 158), (158, 160), (200, 201), (300, 300)]
    s = page_scores(hits, evidence, k=5)
    assert s["recall"] == 1.0
    assert s["rr"] == 0.5
    assert round(s["ndcg"], 4) == round(1 / 1.5849625, 4)  # 1 / log2(3)
    assert s["precision"] == 2 / 5
    assert page_scores(hits, evidence, k=1) == {"recall": 0.0, "rr": 0.0, "ndcg": 0.0, "precision": 0.0}
    assert page_scores([(158, 158)], evidence, k=1)["ndcg"] == 1.0
    assert is_relevant(157, 159, [158]) and not is_relevant(159, 160, [158])
