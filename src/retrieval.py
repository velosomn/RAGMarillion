"""Helpers de recuperação e geração, compartilhados pelos notebooks 05–07."""
from __future__ import annotations

import math
import time

# Versões do prompt da resposta. A avaliação (06) compara versões; a padrão é a mais recente.
PROMPTS = {
    "v1": """Você é um assistente que responde perguntas sobre O Silmarillion.
Regras:
1. Use SOMENTE os trechos fornecidos no contexto. Não use conhecimento prévio.
2. Cite os trechos usados no formato [c00042].
3. Se o contexto não contiver a resposta, diga exatamente: "Não encontrei isso nos trechos recuperados."
4. Responda em português, de forma concisa.""",
    # v2: não exagerar o que o trecho diz ("participou" não vira "criou"), citar o trecho certo,
    # listas completas e resposta parcial em vez de recusa quando há parte da resposta.
    "v2": """Você é um assistente que responde perguntas sobre O Silmarillion.
Regras:
1. Use SOMENTE os trechos fornecidos no contexto. Não use conhecimento prévio sobre o livro.
2. Afirme só o que os trechos dizem, com a mesma força: se um trecho diz que alguém participou, ajudou ou entregou algo, não diga que essa pessoa criou ou fez aquilo sozinha.
3. Logo após cada afirmação, cite o trecho que a contém, no formato [c00042]. Não cite um trecho que não sustenta a afirmação.
4. Se a pergunta pede vários itens (nomes, filhos, lugares), inclua todos os que aparecem nos trechos.
5. Se os trechos tiverem só parte da resposta, responda essa parte e diga o que faltou. Se não tiverem nada da resposta, diga exatamente: "Não encontrei isso nos trechos recuperados."
6. Responda em português, de forma concisa.""",
}
DEFAULT_PROMPT = "v2"


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


def call_with_retries(fn, *args, tries: int = 4, wait_s: float = 20, sleep=time.sleep):
    """Chama fn(*args), repetindo com espera crescente se der erro (ex.: limite de chamadas
    do Free Edition). Depois da última tentativa, deixa o erro subir."""
    for attempt in range(1, tries + 1):
        try:
            return fn(*args)
        except Exception as e:
            if attempt == tries:
                raise
            print(f"Tentativa {attempt} falhou ({type(e).__name__}); nova em {wait_s * attempt:.0f}s")
            sleep(wait_s * attempt)


def indexed_row_count(index) -> int | None:
    return index.describe().get("status", {}).get("indexed_row_count")


def parse_search_result(result: dict) -> list[dict]:
    """Converte a resposta do similarity_search em lista de dicts (inclui 'score')."""
    cols = [c["name"] for c in result["manifest"]["columns"]]
    rows = result.get("result", {}).get("data_array", []) or []
    return [dict(zip(cols, row)) for row in rows]


def format_context(hits: list[dict]) -> str:
    return "\n\n".join(f"[{h['chunk_id']}] ({h['chapter']}, p.{h['page_start']})\n{h['text']}" for h in hits)


def build_messages(question: str, hits: list[dict], prompt_version: str = DEFAULT_PROMPT) -> list[dict]:
    return [
        {"role": "system", "content": PROMPTS[prompt_version]},
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


# --- Métricas por página -------------------------------------------------------
# A relevância é decidida pela página, não pelo chunk: a mesma marcação do gabarito
# vale para qualquer chunking, e a ablação compara configurações de forma justa.

def is_relevant(page_start: int, page_end: int, evidence_pages: list[int]) -> bool:
    """O chunk cobre alguma página onde está a resposta?"""
    return any(page_start <= p <= page_end for p in evidence_pages)


def page_scores(hits: list[tuple[int, int]], evidence_pages: list[int], k: int) -> dict:
    """Métricas de um ranking: `hits` = [(page_start, page_end), ...] na ordem da busca.

    - recall: algum dos k primeiros cobre a resposta (0 ou 1 por pergunta)
    - rr: 1 / posição do primeiro relevante
    - ndcg: relevância binária com uma evidência por pergunta = 1 / log2(1 + posição)
    - precision: fração dos k que cobrem a resposta
    """
    rel = [is_relevant(s, e, evidence_pages) for s, e in hits[:k]]
    first = next((i for i, r in enumerate(rel, start=1) if r), None)
    return {
        "recall": float(first is not None),
        "rr": 1.0 / first if first else 0.0,
        "ndcg": 1.0 / math.log2(1 + first) if first else 0.0,
        "precision": sum(rel) / k if k else 0.0,
    }
