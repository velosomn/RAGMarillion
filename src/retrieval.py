"""Helpers de recuperação e geração, compartilhados pelos notebooks 05–07."""
from __future__ import annotations

import math
import re
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


def distinctive_query(text: str, size: int = 15, margin: int = 60) -> str:
    """Trecho de `size` palavras do chunk para o teste de auto-recuperação: a janela com mais nomes
    próprios, longe das bordas que o chunk divide com os vizinhos (o overlap). Uma frase comum
    ("os orcs se demoravam na estrada") existe em dezenas de chunks e não serve de teste."""
    words = re.sub(r"^\[[^\]]*\]\s*", "", text, count=1).split()  # sem o rótulo do capítulo
    lo, hi = margin, len(words) - margin - size
    if hi < lo:  # chunk curto: janela do meio
        lo = hi = max((len(words) - size) // 2, 0)
    center = (lo + hi) / 2
    best = max(range(lo, hi + 1),
               key=lambda i: (sum(w[:1].isupper() for w in words[i:i + size]), -abs(i - center)))
    return " ".join(words[best:best + size])


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


# --- Estratégias de busca ------------------------------------------------------
# Funções puras que escolhem e ordenam os trechos; quem chama o índice é src/rag.py.
# Cada trecho ("hit") é um dict com chunk_id, chapter, page_start, page_end e text.

STRATEGIES = ("simples", "vizinhos", "diversa", "por_nome")

# Palavras que começam perguntas com maiúscula sem serem nomes
QUESTION_STARTERS = {"quem", "qual", "quais", "onde", "quando", "como", "por", "porque", "que", "quanto",
                     "quantos", "quantas", "o", "a", "os", "as", "um", "uma", "em", "de", "do", "da", "dos",
                     "das", "no", "na", "nos", "nas", "para", "com", "segundo", "após", "depois", "antes",
                     "durante", "ao", "aos", "à", "às", "e", "se", "há", "houve", "foi", "era", "existe"}
_NAME_TOKEN = re.compile(r"[\w'-]+")


def proper_nouns(question: str) -> list[str]:
    """Nomes próprios da pergunta, juntando palavras seguidas com maiúscula ("Nirnaeth Arnoediad")."""
    names, current = [], []
    for i, token in enumerate(_NAME_TOKEN.findall(question)):
        if token[:1].isupper() and not (i == 0 and token.casefold() in QUESTION_STARTERS):
            current.append(token)
        elif current:
            names.append(" ".join(current))
            current = []
    if current:
        names.append(" ".join(current))
    return list(dict.fromkeys(names))


def select_diverse(hits: list[dict], k: int, max_per_chapter: int = 2) -> list[dict]:
    """Os k melhores, com no máximo `max_per_chapter` do mesmo capítulo; completa com o resto se faltar."""
    chosen, per_chapter = [], {}
    for h in hits:
        if per_chapter.get(h["chapter"], 0) < max_per_chapter:
            chosen.append(h)
            per_chapter[h["chapter"]] = per_chapter.get(h["chapter"], 0) + 1
        if len(chosen) == k:
            return chosen
    chosen_ids = {h["chunk_id"] for h in chosen}
    return chosen + [h for h in hits if h["chunk_id"] not in chosen_ids][: k - len(chosen)]


def round_robin(lists: list[list[dict]], k: int) -> list[dict]:
    """Intercala várias listas de resultados (1º de cada, depois 2º de cada...) sem repetir, até k."""
    out, seen = [], set()
    for i in range(max((len(lst) for lst in lists), default=0)):
        for lst in lists:
            if i < len(lst) and lst[i]["chunk_id"] not in seen:
                out.append(lst[i])
                seen.add(lst[i]["chunk_id"])
                if len(out) == k:
                    return out
    return out


def neighbor_ids(chunk_id: str) -> list[str]:
    """Ids do trecho anterior e do seguinte ("c00421" → "c00420", "c00422")."""
    n = int(chunk_id[1:])
    return [f"c{m:05d}" for m in (n - 1, n + 1) if m >= 0]


def with_neighbors(hits: list[dict], neighbors: dict[str, dict], expand_top: int) -> list[dict]:
    """Insere, em volta de cada um dos `expand_top` primeiros trechos, o anterior e o seguinte do mesmo
    capítulo, na ordem do livro; os demais trechos seguem na ordem da busca, sem repetir."""
    out, seen = [], set()

    def add(h):
        if h is not None and h["chunk_id"] not in seen:
            out.append(h)
            seen.add(h["chunk_id"])

    for i, h in enumerate(hits):
        if i < expand_top:
            n = int(h["chunk_id"][1:])
            prev, nxt = neighbors.get(f"c{n - 1:05d}"), neighbors.get(f"c{n + 1:05d}")
            add(prev if prev and prev["chapter"] == h["chapter"] else None)
            add(h)
            add(nxt if nxt and nxt["chapter"] == h["chapter"] else None)
        else:
            add(h)
    return out
