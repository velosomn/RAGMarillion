"""Limpeza de texto e chunking com consciência de capítulo.

Funções puras (sem Spark) para poder testar localmente com pytest.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Iterator

FRONT_MATTER = "Início"  # capítulo dos chunks que vêm antes do primeiro título
MAX_HEADING_WORDS = 15   # linha mais longa que isso nunca é título


@dataclass
class Chunk:
    chunk_id: str
    chapter: str
    page_start: int
    page_end: int
    chunk_index: int
    n_words: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_SPACE = re.compile(r"[ \t]+")
# Ligaduras tipográficas do PDF (ﬁ, ﬂ...): na tela parecem "fi", mas para a busca
# "ﬁlhos" e "filhos" seriam palavras diferentes.
_LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})


def clean_page(text: str, drop_line_patterns: list[str] | None = None) -> str:
    """Normaliza acentos (NFC) e ligaduras, remove hifenização de quebra de linha,
    espaços repetidos e linhas de ruído (cabeçalho corrente, número de página)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(_LIGATURES)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    patterns = [re.compile(p) for p in (drop_line_patterns or [r"^\s*\d{1,4}\s*$"])]
    lines = []
    for line in text.splitlines():
        if any(p.match(line) for p in patterns):
            continue
        lines.append(_MULTI_SPACE.sub(" ", line).strip())
    return "\n".join(lines)


def normalize_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def iter_blocks(pages: list[tuple[int, str]], chapter_regex: str | None = None) -> Iterator[tuple[str, int, str]]:
    """Percorre as páginas linha a linha e gera ("heading" | "para", página, texto).

    Títulos são detectados por linha, não por parágrafo: o pypdf costuma extrair o texto
    sem linha em branco entre parágrafos, e o título ficaria grudado no texto seguinte.
    Um título longo quebrado em várias linhas em maiúsculas é juntado numa só.
    Linha vazia separa parágrafo; linhas soltas do PDF são unidas com espaço.
    """
    chap_re = re.compile(chapter_regex) if chapter_regex else None
    for page_num, text in pages:
        buf: list[str] = []
        lines = [line.strip() for line in text.splitlines()]
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            if chap_re and chap_re.match(line) and len(line.split()) <= MAX_HEADING_WORDS:
                if buf:
                    yield "para", page_num, " ".join(buf)
                    buf = []
                while (i < len(lines) and lines[i].isupper()
                       and len(line.split()) + len(lines[i].split()) <= MAX_HEADING_WORDS):
                    line = f"{line} {lines[i]}"
                    i += 1
                yield "heading", page_num, line
            elif line:
                buf.append(line)
            elif buf:
                yield "para", page_num, " ".join(buf)
                buf = []
        if buf:
            yield "para", page_num, " ".join(buf)


def split_paragraphs(text: str) -> list[str]:
    """Junta linhas em parágrafos (sem detecção de título)."""
    return [t for _, _, t in iter_blocks([(0, text)])]


def find_headings(pages: list[tuple[int, str]], chapter_regex: str | None) -> list[dict]:
    """Títulos detectados, na ordem. `repeat=True` marca um título igual ao anterior
    (típico de cabeçalho corrente com o nome do capítulo), que o chunking ignora."""
    out, prev = [], None
    for kind, page, text in iter_blocks(pages, chapter_regex):
        if kind == "heading":
            norm = normalize_title(text)
            out.append({"page": page, "title": text, "repeat": norm == prev})
            prev = norm
    return out


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size_words: int = 350,
    overlap_words: int = 60,
    chapter_regex: str | None = None,
    prepend_chapter: bool = True,
) -> list[Chunk]:
    """Gera chunks a partir de [(page_number, cleaned_text), ...].

    - Uma linha que bate em `chapter_regex` fecha o chunk atual e inicia capítulo novo
      (chunks nunca atravessam capítulos). Um título igual ao do capítulo atual é ignorado.
    - Parágrafos são acumulados até ~chunk_size_words; o próximo chunk começa com as
      últimas `overlap_words` palavras do anterior.
    - Parágrafo maior que o chunk é fatiado por palavras.
    """
    if overlap_words >= chunk_size_words:
        raise ValueError("overlap_words precisa ser menor que chunk_size_words")

    chunks: list[Chunk] = []
    chapter = FRONT_MATTER
    buf_words: list[str] = []
    buf_pages: list[int] = []
    fresh = 0  # palavras novas no buffer, além do overlap
    idx_in_chapter = 0

    def flush(keep_overlap: bool) -> None:
        nonlocal buf_words, buf_pages, idx_in_chapter, fresh
        if fresh:  # buffer só com overlap repetiria o fim do chunk anterior
            body = " ".join(buf_words)
            text = f"[{chapter}] {body}" if prepend_chapter else body
            chunks.append(
                Chunk(
                    chunk_id=f"c{len(chunks):05d}",
                    chapter=chapter,
                    page_start=min(buf_pages),
                    page_end=max(buf_pages),
                    chunk_index=idx_in_chapter,
                    n_words=len(buf_words),
                    text=text,
                )
            )
            idx_in_chapter += 1
        if keep_overlap and overlap_words > 0:
            buf_words = buf_words[-overlap_words:]
            buf_pages = buf_pages[-1:]
        else:
            buf_words, buf_pages = [], []
        fresh = 0

    for kind, page_num, text in iter_blocks(pages, chapter_regex):
        if kind == "heading":
            if normalize_title(text) == normalize_title(chapter):
                continue
            flush(keep_overlap=False)
            chapter, idx_in_chapter = text, 0
            continue
        words = text.split()
        while words:
            room = chunk_size_words - len(buf_words)
            take, words = words[:room], words[room:]
            buf_words.extend(take)
            buf_pages.append(page_num)
            fresh += len(take)
            if len(buf_words) >= chunk_size_words:
                flush(keep_overlap=True)
    flush(keep_overlap=False)
    return chunks
