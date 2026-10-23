"""Limpeza de texto e chunking com consciência de capítulo.

Funções puras (sem Spark) para poder testar localmente com pytest.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict


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


def clean_page(text: str, drop_line_patterns: list[str] | None = None) -> str:
    """Remove hifenização de quebra de linha, espaços repetidos e linhas de ruído
    (cabeçalho corrente, número de página) definidas por regex."""
    if not text:
        return ""
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    patterns = [re.compile(p) for p in (drop_line_patterns or [r"^\s*\d{1,4}\s*$"])]
    lines = []
    for line in text.splitlines():
        if any(p.match(line) for p in patterns):
            continue
        lines.append(_MULTI_SPACE.sub(" ", line).strip())
    return "\n".join(lines)


def split_paragraphs(text: str) -> list[str]:
    """Junta linhas em parágrafos. Linha vazia separa parágrafo; linhas
    soltas do PDF são unidas com espaço."""
    paras, buf = [], []
    for line in text.splitlines():
        if not line.strip():
            if buf:
                paras.append(" ".join(buf))
                buf = []
        else:
            buf.append(line.strip())
    if buf:
        paras.append(" ".join(buf))
    return paras


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size_words: int = 350,
    overlap_words: int = 60,
    chapter_regex: str | None = None,
    prepend_chapter: bool = True,
) -> list[Chunk]:
    """Gera chunks a partir de [(page_number, cleaned_text), ...].

    - Um título que bate em `chapter_regex` fecha o chunk atual e inicia capítulo novo
      (chunks nunca atravessam capítulos).
    - Parágrafos são acumulados até ~chunk_size_words; o próximo chunk começa com as
      últimas `overlap_words` palavras do anterior.
    - Parágrafo maior que o chunk é fatiado por palavras.
    """
    if overlap_words >= chunk_size_words:
        raise ValueError("overlap_words precisa ser menor que chunk_size_words")
    chap_re = re.compile(chapter_regex) if chapter_regex else None

    chunks: list[Chunk] = []
    chapter = "Início"
    buf_words: list[str] = []
    buf_pages: list[int] = []
    idx_in_chapter = 0

    def flush(keep_overlap: bool) -> None:
        nonlocal buf_words, buf_pages, idx_in_chapter
        if not buf_words:
            return
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

    for page_num, page_text in pages:
        for para in split_paragraphs(page_text):
            if chap_re and chap_re.match(para) and len(para.split()) <= 15:
                flush(keep_overlap=False)
                chapter = para.strip()
                idx_in_chapter = 0
                continue
            words = para.split()
            while words:
                room = chunk_size_words - len(buf_words)
                take, words = words[:room], words[room:]
                buf_words.extend(take)
                buf_pages.append(page_num)
                if len(buf_words) >= chunk_size_words:
                    flush(keep_overlap=True)
    flush(keep_overlap=False)
    return chunks
