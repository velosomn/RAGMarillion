"""Gabarito sintético: um LLM lê UM chunk e escreve uma pergunta que aquele trecho responde.

Funções puras (sem Spark nem LLM) para o notebook 06a e para os testes. O chunk e a página
de origem vêm do sorteio, não do LLM: são eles que permitem medir a recuperação.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from src.chunking import normalize_title

SYSTEM_PROMPT = "Você cria perguntas de avaliação a partir de um trecho de livro."

USER_PROMPT = """Trecho:
{text}

Escreva UMA pergunta que este trecho responde e a resposta.
Regras:
1. Use apenas o que está no trecho, não o que você sabe sobre o livro.
2. A pergunta deve se entender sozinha: cite os nomes, nunca "ele", "ela" ou "isso" sem dizer quem ou o quê.
3. Não copie frases do trecho; reformule com suas palavras.
4. A resposta deve ser curta, com até 20 palavras.
5. Liste de 1 a 3 termos-chave da resposta que aparecem exatamente assim no trecho.
Responda só com JSON, sem comentários: {{"pergunta": "...", "resposta": "...", "termos": ["..."]}}"""

DISCARD_REASONS = ("json_invalido", "campos_faltando", "termo_fora_do_trecho",
                   "sem_nome_proprio", "copia_do_trecho", "resposta_longa")

_PREFIX = re.compile(r"^\[[^\]]*\]\s*")
_JSON = re.compile(r"\{.*\}", re.DOTALL)
_WORD = re.compile(r"\w+")


def strip_chapter_prefix(text: str) -> str:
    """Tira o "[CAPÍTULO ...] " que o chunking põe no início do texto."""
    return _PREFIX.sub("", text, count=1)


def build_messages(chunk_text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT.format(text=strip_chapter_prefix(chunk_text))},
    ]


def parse_generation(raw: str) -> dict | None:
    """Extrai o JSON da resposta do LLM (ele às vezes embrulha em ```json ... ```)."""
    match = _JSON.search(raw or "")
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _fold(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


# Palavras que começam perguntas com maiúscula sem serem nomes
_QUESTION_STARTERS = {"quem", "qual", "quais", "onde", "quando", "como", "por", "porque", "que", "quanto",
                      "quantos", "quantas", "o", "a", "os", "as", "um", "uma", "em", "de", "do", "da", "dos",
                      "das", "no", "na", "nos", "nas", "para", "com", "segundo", "após", "depois", "antes",
                      "durante", "ao", "aos", "à", "às", "e", "se", "há", "houve", "foi", "era", "existe"}


def has_proper_noun(question: str) -> bool:
    """Alguma palavra com maiúscula que seja um nome (a primeira conta, se não for "Quem", "Onde"...)."""
    words = _WORD.findall(question)
    return any(w[0].isupper() and (i > 0 or w.casefold() not in _QUESTION_STARTERS)
               for i, w in enumerate(words))


def longest_shared_run(a: str, b: str) -> int:
    """Maior sequência de palavras seguidas que aparece igual nos dois textos."""
    wa = [w.casefold() for w in _WORD.findall(a)]
    wb = [w.casefold() for w in _WORD.findall(b)]
    best, prev = 0, [0] * (len(wb) + 1)
    for x in wa:
        cur = [0] * (len(wb) + 1)
        for j, y in enumerate(wb, start=1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def check_generation(gen: dict | None, chunk_text: str, max_copy_words: int,
                     max_answer_words: int = 25) -> str | None:
    """Motivo do descarte, ou None se a pergunta pode entrar no gabarito."""
    if gen is None:
        return "json_invalido"
    question, answer, terms = gen.get("pergunta"), gen.get("resposta"), gen.get("termos")
    if not (isinstance(question, str) and question.strip() and isinstance(answer, str) and answer.strip()
            and isinstance(terms, list) and terms and all(isinstance(t, str) and t.strip() for t in terms)):
        return "campos_faltando"
    body = _fold(strip_chapter_prefix(chunk_text))
    if any(_fold(t.strip()) not in body for t in terms):
        return "termo_fora_do_trecho"
    if not has_proper_noun(question):
        return "sem_nome_proprio"
    if longest_shared_run(question, strip_chapter_prefix(chunk_text)) >= max_copy_words:
        return "copia_do_trecho"
    if len(answer.split()) > max_answer_words:
        return "resposta_longa"
    return None


def split_for(question_id: str, test_every: int = 3) -> str:
    """Divisão fixa por id: cerca de 1 em cada `test_every` perguntas vai para teste."""
    h = int(hashlib.md5(question_id.encode("utf-8")).hexdigest(), 16)
    return "test" if h % test_every == 0 else "dev"


def is_excluded(chapter: str, prefixes: list[str]) -> bool:
    """Capítulos de apoio (glossário, mapas...) não geram perguntas sobre a história."""
    norm = normalize_title(chapter)
    return any(norm.startswith(normalize_title(p)) for p in prefixes)
