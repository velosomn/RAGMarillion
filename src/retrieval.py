"""Helpers de recuperação e geração, compartilhados pelos notebooks 05–07."""
from __future__ import annotations

import time

SYSTEM_PROMPT = """Você é um assistente que responde perguntas sobre O Silmarillion.
Regras:
1. Use SOMENTE os trechos fornecidos no contexto. Não use conhecimento prévio.
2. Cite os trechos usados no formato [c00042].
3. Se o contexto não contiver a resposta, diga exatamente: "Não encontrei isso nos trechos recuperados."
4. Responda em português, de forma concisa."""


def wait_for_endpoint(vsc, name: str, timeout_s: int = 1800) -> None:
    """Espera o endpoint de Vector Search ficar ONLINE."""
    start = time.time()
    while True:
        state = vsc.get_endpoint(name).get("endpoint_status", {}).get("state", "UNKNOWN")
        print(f"Endpoint {name}: {state}")
        if state == "ONLINE":
            return
        if "FAIL" in state or time.time() - start > timeout_s:
            raise RuntimeError(f"Endpoint {name} não ficou ONLINE (estado: {state})")
        time.sleep(20)


def wait_until(condition, timeout_s: int = 900, interval_s: int = 20, what: str = "condição") -> bool:
    """Chama `condition()` até ela ser verdadeira ou o tempo acabar. Devolve se conseguiu."""
    start = time.time()
    while not condition():
        if time.time() - start > timeout_s:
            return False
        print(f"Aguardando {what}...")
        time.sleep(interval_s)
    return True


def indexed_row_count(index) -> int | None:
    return index.describe().get("status", {}).get("indexed_row_count")


def parse_search_result(result: dict) -> list[dict]:
    """Converte a resposta do similarity_search em lista de dicts (inclui 'score')."""
    cols = [c["name"] for c in result["manifest"]["columns"]]
    rows = result.get("result", {}).get("data_array", []) or []
    return [dict(zip(cols, row)) for row in rows]


def format_context(hits: list[dict]) -> str:
    return "\n\n".join(f"[{h['chunk_id']}] ({h['chapter']}, p.{h['page_start']})\n{h['text']}" for h in hits)


def build_messages(question: str, hits: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Contexto:\n{format_context(hits)}\n\nPergunta: {question}"},
    ]


def hit_at_k(hits: list[dict], expected_terms: list[str]) -> bool:
    """Proxy de recall: algum chunk recuperado menciona algum termo esperado?"""
    if not expected_terms:
        return False
    blob = " ".join(h["text"].lower() for h in hits)
    return any(t.lower() in blob for t in expected_terms)


def reciprocal_rank(hits: list[dict], expected_terms: list[str]) -> float:
    for i, h in enumerate(hits, start=1):
        if any(t.lower() in h["text"].lower() for t in expected_terms):
            return 1.0 / i
    return 0.0
