"""Formatação da resposta para o terminal: fontes citadas com capítulo e página.

Funções puras (sem MLflow nem Databricks), para testar localmente.
"""
from __future__ import annotations

import re

_CITATION = re.compile(r"\bc\d{5}\b")
_PREFIX = re.compile(r"^\[[^\]]*\]\s*")


def cited_ids(answer: str) -> list[str]:
    """Ids citados na resposta, na ordem em que aparecem, sem repetir."""
    return list(dict.fromkeys(_CITATION.findall(answer or "")))


def page_label(metadata: dict) -> str:
    start = int(metadata["page_start"])
    end = int(metadata.get("page_end") or start)
    return f"p. {start}" if start == end else f"p. {start}–{end}"


def format_sources(answer: str, docs: list) -> list[str]:
    """Uma linha por trecho citado: "[c00078] CAPÍTULO VII: ..., p. 158"."""
    by_id = {d.id: d for d in docs}
    lines = []
    for cid in cited_ids(answer):
        doc = by_id.get(cid)
        if doc is None:
            lines.append(f"[{cid}] (não estava entre os trechos recuperados)")
        else:
            lines.append(f"[{cid}] {doc.metadata['chapter']}, {page_label(doc.metadata)}")
    return lines


def batch_entry(item: dict, answer: str, docs: list) -> str:
    """Uma pergunta do lote em markdown: pergunta, resposta esperada, resposta, fontes citadas e
    ids recuperados. Sem o texto dos trechos, que tem direitos autorais."""
    lines = [f"## {item.get('id', '?')} · {item['question']}", ""]
    if item.get("category"):
        lines += [f"Categoria: {item['category']}", ""]
    if item.get("expected_response"):
        lines += [f"**Esperada:** {item['expected_response']}", ""]
    quoted = [f"> {line}" if line.strip() else ">" for line in (answer or "").strip().splitlines()]
    lines += ["**Resposta:**", ""] + (quoted or ["> (vazia)"]) + [""]
    sources = format_sources(answer, docs)
    lines += ["**Fontes:**", ""] + ([f"- {s}" for s in sources] or ["- nenhuma citada"]) + [""]
    lines += ["Recuperados: " + (", ".join(f"`{d.id}`" for d in docs) or "nenhum"), ""]
    return "\n".join(lines)


def excerpt(text: str, max_chars: int | None = 300) -> str:
    """Começo do trecho (ou ele inteiro, com max_chars=None), sem o rótulo do capítulo e numa linha só."""
    body = " ".join(_PREFIX.sub("", text, count=1).split())
    if max_chars is None or len(body) <= max_chars:
        return body
    return body[:max_chars].rsplit(" ", 1)[0] + "…"
