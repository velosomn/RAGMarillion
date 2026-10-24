"""Verificações de qualidade de cada etapa do pipeline.

Funções puras: recebem dados já carregados e devolvem um `Result`. O notebook decide o
nível (ERRO para a execução, AVISO só registra) e junta tudo num `Report`.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from src.chunking import FRONT_MATTER, MAX_HEADING_WORDS, Chunk, iter_blocks, normalize_title

LEVELS = ("ERRO", "AVISO")
EVAL_CATEGORIES = ("factual", "aliases", "similar_names", "multi_hop", "unanswerable", "sintetica")


@dataclass
class Result:
    ok: bool
    detail: str


class Report:
    """Junta os resultados de uma etapa; `finish()` mostra o resumo e para se houver ERRO."""

    def __init__(self, stage: str):
        self.stage = stage
        self.rows: list[tuple[str, str, str]] = []  # (status, nome, detalhe)

    def add(self, name: str, result: Result, level: str = "ERRO") -> Result:
        if level not in LEVELS:
            raise ValueError(f"level deve ser um de {LEVELS}")
        self.rows.append(("OK" if result.ok else level, name, result.detail))
        return result

    def info(self, name: str, detail: str) -> None:
        self.rows.append(("INFO", name, detail))

    def errors(self) -> list[str]:
        return [name for status, name, _ in self.rows if status == "ERRO"]

    def finish(self) -> None:
        print(f"=== Verificações · {self.stage} ===")
        for status, name, detail in self.rows:
            print(f"[{status:<5}] {name}: {detail}")
        if self.errors():
            raise RuntimeError(
                f"{len(self.errors())} verificação(ões) com ERRO em {self.stage}: "
                f"{', '.join(self.errors())}. Veja o resumo acima."
            )


def _fold(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def count_words(pages: list[tuple[int, str]]) -> int:
    return sum(len(t.split()) for _, t in pages)


# --- 02 · Ingestão -----------------------------------------------------------

def empty_pages(pages: list[tuple[int, str]], max_frac: float) -> Result:
    empty = [n for n, t in pages if not t.strip()]
    frac = len(empty) / max(len(pages), 1)
    detail = f"{len(empty)} de {len(pages)} páginas ({frac:.0%}); limite {max_frac:.0%}"
    if frac > max_frac:
        detail += ". O PDF provavelmente é escaneado e precisa de OCR."
    return Result(frac <= max_frac, detail)


def total_words(pages: list[tuple[int, str]], min_words: int) -> Result:
    n = count_words(pages)
    detail = f"{n:,} palavras; mínimo {min_words:,}"
    if n < min_words:
        detail += ". Arquivo errado ou incompleto?"
    return Result(n >= min_words, detail)


def anchor_terms(pages: list[tuple[int, str]], terms: list[str], min_frac: float) -> Result:
    if not terms:
        return Result(True, "nenhum termo configurado")
    blob = _fold(" ".join(t for _, t in pages))
    missing = [t for t in terms if _fold(t) not in blob]
    found = len(terms) - len(missing)
    ok = found / len(terms) >= min_frac
    detail = f"{found}/{len(terms)} encontrados"
    if missing:
        detail += f"; faltando: {', '.join(missing)}"
    if not ok:
        detail += ". Livro errado ou acentos quebrados na extração (ex.: 'F¨eanor' em vez de 'Fëanor')."
    return Result(ok, detail)


# caractere de substituição, ligaduras (ﬁ, ﬂ...) e acento solto colado numa letra
_BAD_CHARS = re.compile(r"[�ﬀ-ﬆ]|\w[¨´˜ˆ]|[¨´˜ˆ]\w")


def bad_chars(pages: list[tuple[int, str]], max_frac: float) -> Result:
    blob = " ".join(t for _, t in pages)
    matches = list(_BAD_CHARS.finditer(blob))
    frac = len(matches) / max(len(blob), 1)
    detail = f"{len(matches)} ocorrências ({frac:.4%} dos caracteres)"
    if matches:
        # mostra o código do caractere: ligaduras como "ﬁ" parecem texto normal na tela
        kinds = Counter(next(c for c in m.group() if not c.isalnum() or ord(c) > 0xFAFF) for m in matches)
        detail += "; tipos: " + ", ".join(f"'{c}' (U+{ord(c):04X}) ×{n}" for c, n in kinds.most_common())
        examples = [blob[max(m.start() - 15, 0):m.end() + 15].replace("\n", " ") for m in matches[:3]]
        detail += "; exemplos: " + " | ".join(repr(e) for e in examples)
    return Result(frac <= max_frac, detail)


_DIGITS = re.compile(r"\d+")


def suggest_pattern(key: str) -> str:
    """Regex para DROP_LINE_PATTERNS a partir de uma linha com números trocados por #."""
    # o clean_page compara com a linha crua, antes de juntar espaços repetidos
    words = [r"\d+".join(re.escape(part) for part in word.split("#")) for word in key.split()]
    return r"^\s*" + r"\s+".join(words) + r"\s*$"


def repeated_lines(pages: list[tuple[int, str]], min_frac: float, edge_lines: int = 2,
                   min_pages: int = 5) -> Result:
    """Linhas do topo/rodapé que se repetem em muitas páginas (números trocados por #).
    Sugere um padrão para DROP_LINE_PATTERNS."""
    counts: Counter[str] = Counter()
    for _, text in pages:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        edges = lines[:edge_lines] + lines[-edge_lines:]
        counts.update({_DIGITS.sub("#", line) for line in edges})
    threshold = max(min_pages, min_frac * len(pages))
    frequent = [(key, n) for key, n in counts.most_common() if n >= threshold]
    if not frequent:
        return Result(True, "nenhuma linha de topo/rodapé se repete com frequência")
    suggestions = [f"'{key}' em {n} páginas → r\"{suggest_pattern(key)}\"" for key, n in frequent]
    return Result(False, "provável cabeçalho/rodapé; adicione em DROP_LINE_PATTERNS:\n    " + "\n    ".join(suggestions))


# --- 03 · Chunking -----------------------------------------------------------

def chapter_count(headings: list[dict], expected: tuple[int, int]) -> Result:
    n = sum(not h["repeat"] for h in headings)
    lo, hi = expected
    detail = f"{n} capítulos detectados; esperado entre {lo} e {hi}"
    if n < lo:
        detail += ". O CHAPTER_REGEX não está pegando todos os títulos."
    elif n > hi:
        detail += ". O CHAPTER_REGEX está pegando frases comuns ou cabeçalhos."
    return Result(lo <= n <= hi, detail)


def duplicate_headings(headings: list[dict]) -> Result:
    """Um título que reaparece depois de outro capítulo indica cabeçalho corrente
    alternado (ex.: nome do livro numa página, do capítulo na outra)."""
    counts = Counter(normalize_title(h["title"]) for h in headings if not h["repeat"])
    dups = [h["title"] for h in headings if not h["repeat"] and counts[normalize_title(h["title"])] > 1]
    ignored = sum(h["repeat"] for h in headings)
    detail = f"{ignored} repetições seguidas ignoradas (provável cabeçalho com o nome do capítulo)"
    if dups:
        pages = [h["page"] for h in headings if not h["repeat"] and h["title"] in dups]
        detail = (f"títulos que reaparecem depois de outro capítulo: {sorted(set(dups))} "
                  f"(páginas {pages}). Provável cabeçalho corrente: remova com DROP_LINE_PATTERNS. " + detail)
    return Result(not dups, detail)


def long_heading_lines(pages: list[tuple[int, str]], chapter_regex: str) -> Result:
    """Linhas que batem no regex mas foram descartadas por serem longas demais."""
    chap_re = re.compile(chapter_regex)
    long_lines = [
        (n, line.strip()) for n, t in pages for line in t.splitlines()
        if chap_re.match(line.strip()) and len(line.split()) > MAX_HEADING_WORDS
    ]
    if not long_lines:
        return Result(True, "nenhuma")
    shown = "; ".join(f"p.{n}: {line[:80]}…" for n, line in long_lines[:5])
    return Result(False, f"{len(long_lines)} linha(s) com mais de {MAX_HEADING_WORDS} palavras ignoradas "
                         f"(título grudado no texto?): {shown}")


def small_chapters(chunks: list[Chunk], min_chunks: int) -> Result:
    counts = Counter(c.chapter for c in chunks if c.chapter != FRONT_MATTER)
    small = {ch: n for ch, n in counts.items() if n < min_chunks}
    if not small:
        return Result(True, f"todos com pelo menos {min_chunks} chunks")
    return Result(False, f"capítulos com menos de {min_chunks} chunks (frase comum confundida com título?): {small}")


def dominant_chapter(chunks: list[Chunk], max_share: float) -> Result:
    if not chunks:
        return Result(False, "nenhum chunk")
    chapter, n = Counter(c.chapter for c in chunks).most_common(1)[0]
    share = n / len(chunks)
    detail = f"maior capítulo: '{chapter}' com {share:.0%} dos chunks; limite {max_share:.0%}"
    if share > max_share:
        detail += ". Algum título não foi detectado."
    return Result(share <= max_share, detail)


def short_chunks(chunks: list[Chunk], min_words: int, max_frac: float) -> Result:
    short = [c.chunk_id for c in chunks if c.n_words < min_words]
    frac = len(short) / max(len(chunks), 1)
    detail = f"{len(short)} de {len(chunks)} chunks com menos de {min_words} palavras ({frac:.0%}); limite {max_frac:.0%}"
    if short:
        detail += f"; ex.: {short[:5]}"
    return Result(frac <= max_frac, detail)


def word_coverage(pages: list[tuple[int, str]], chunks: list[Chunk], chapter_regex: str | None,
                  overlap_words: int, max_lost_frac: float) -> Result:
    """Palavras das páginas (fora os títulos) × palavras nos chunks, descontando o overlap."""
    expected = sum(len(t.split()) for kind, _, t in iter_blocks(pages, chapter_regex) if kind == "para")
    continuing = sum(1 for c in chunks if c.chunk_index > 0)  # começam com o overlap do anterior
    got = sum(c.n_words for c in chunks) - overlap_words * continuing
    lost = (expected - got) / max(expected, 1)
    return Result(abs(lost) <= max_lost_frac,
                  f"{got:,} de {expected:,} palavras nos chunks (diferença {lost:.2%}); limite {max_lost_frac:.0%}")


# --- 04 · Índice -------------------------------------------------------------

def index_rows(indexed: int | None, expected: int) -> Result:
    return Result(indexed == expected, f"{indexed} linhas no índice; {expected} na tabela de chunks")


def self_retrieval(hits: list[tuple[str, list[str]]]) -> Result:
    """`hits` = [(chunk_id buscado pelo próprio texto, ids recuperados)]. Pelo menos metade
    precisa voltar no top-k."""
    misses = [cid for cid, ids in hits if cid not in ids]
    found = len(hits) - len(misses)
    detail = f"{found}/{len(hits)} chunks encontrados buscando um trecho do próprio texto"
    if misses:
        detail += f"; não encontrados: {misses}"
    return Result(found * 2 >= len(hits) > 0, detail)


# --- 05 · Cadeia RAG ---------------------------------------------------------

_CITATION = re.compile(r"\bc\d{5}\b")


def citations(answer: str, retrieved_ids: list[str], refusal_text: str) -> Result:
    if refusal_text.lower() in answer.lower():
        return Result(True, "recusou (sem citação, como esperado)")
    cited = sorted(set(_CITATION.findall(answer)))
    if not cited:
        return Result(False, "resposta sem nenhuma citação")
    invented = [c for c in cited if c not in retrieved_ids]
    if invented:
        return Result(False, f"cita trechos que não foram recuperados: {invented}")
    return Result(True, f"{len(cited)} citação(ões) válida(s)")


# --- 06 · Avaliação ----------------------------------------------------------

def validate_eval_set(eval_set: list[dict]) -> Result:
    required = ("id", "category", "question", "expected_response", "expected_terms")
    problems = []
    for i, e in enumerate(eval_set, start=1):
        qid = e.get("id", f"linha {i}")
        missing = [k for k in required if k not in e]
        if missing:
            problems.append(f"{qid}: faltam {missing}")
            continue
        if e["category"] not in EVAL_CATEGORIES:
            problems.append(f"{qid}: categoria '{e['category']}' inválida")
        if e["category"] != "unanswerable" and not e["expected_terms"]:
            problems.append(f"{qid}: expected_terms vazio")
    dup_ids = [i for i, n in Counter(e.get("id") for e in eval_set).items() if n > 1]
    if dup_ids:
        problems.append(f"ids repetidos: {dup_ids}")
    if not problems:
        return Result(True, f"{len(eval_set)} perguntas bem formadas")
    return Result(False, "; ".join(problems))


def missing_terms(eval_set: list[dict], texts: list[str]) -> dict[str, list[str]]:
    """Para cada pergunta respondível: termos esperados que não aparecem em nenhum chunk."""
    blob = _fold(" ".join(texts))
    return {
        e["id"]: [t for t in e["expected_terms"] if _fold(t) not in blob]
        for e in eval_set if e["category"] != "unanswerable"
    }


def unreachable_questions(eval_set: list[dict], missing: dict[str, list[str]]) -> list[str]:
    """Perguntas em que nenhum termo esperado está no corpus: hit@k seria sempre zero."""
    return [e["id"] for e in eval_set
            if e["category"] != "unanswerable" and len(missing[e["id"]]) == len(e["expected_terms"])]


def absent_terms(missing: dict[str, list[str]]) -> Result:
    absent = {qid: terms for qid, terms in missing.items() if terms}
    if not absent:
        return Result(True, "todos os termos esperados aparecem no texto")
    return Result(False, f"termos que não aparecem no texto (grafia da sua edição?): {absent}")
