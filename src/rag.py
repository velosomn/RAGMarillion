"""Cadeia RAG instrumentada com MLflow Tracing."""
from __future__ import annotations

import mlflow
from mlflow.entities import Document, SpanType
from mlflow.deployments import get_deploy_client

from src.retrieval import (DEFAULT_PROMPT, STRATEGIES, build_messages, neighbor_ids, parse_search_result,
                           proper_nouns, round_robin, select_diverse, with_neighbors)

COLUMNS = ["chunk_id", "chapter", "page_start", "page_end", "text"]

CLOSED_BOOK_PROMPT = """Você responde perguntas sobre O Silmarillion, de J.R.R. Tolkien, de memória.
Responda em português, de forma concisa."""


class RAGMarillion:
    def __init__(self, index, llm_endpoint: str, top_k: int = 5, query_type: str = "hybrid",
                 temperature: float = 0.0, max_tokens: int = 500, prompt_version: str = DEFAULT_PROMPT,
                 strategy: str = "simples", pool: int = 20, max_per_chapter: int = 2, expand_top: int = 2):
        """strategy (veja STRATEGIES em src/retrieval.py):
        - simples: os top_k trechos mais parecidos com a pergunta
        - vizinhos: os top_k, mais o anterior e o seguinte dos `expand_top` primeiros (mesmo capítulo)
        - diversa: dos `pool` melhores, top_k com no máximo `max_per_chapter` por capítulo
        - por_nome: uma busca por nome próprio da pergunta, intercalada com a busca da pergunta inteira"""
        if strategy not in STRATEGIES:
            raise ValueError(f"strategy deve ser uma de {STRATEGIES}")
        self.index = index
        self.llm_endpoint = llm_endpoint
        self.top_k = top_k
        self.query_type = query_type
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.prompt_version = prompt_version
        self.strategy = strategy
        self.pool = pool
        self.max_per_chapter = max_per_chapter
        self.expand_top = expand_top
        self.client = get_deploy_client("databricks")
        self.last_docs: list[Document] = []  # chunks usados na última chamada de answer()

    def _search(self, query: str, n: int, filters: dict | None = None, query_type: str | None = None) -> list[dict]:
        extra = {"filters": filters} if filters else {}
        res = self.index.similarity_search(
            query_text=query,
            columns=COLUMNS,
            num_results=n,
            query_type=query_type or self.query_type,
            disable_notice=True,
            **extra,
        )
        return parse_search_result(res)

    @mlflow.trace(span_type=SpanType.RETRIEVER)
    def retrieve(self, question: str) -> list[Document]:
        if self.strategy == "diversa":
            hits = select_diverse(self._search(question, self.pool), self.top_k, self.max_per_chapter)
        elif self.strategy == "por_nome":
            names = proper_nouns(question)[:3]
            lists = [self._search(question, self.top_k)] + [self._search(name, 3) for name in names]
            hits = round_robin(lists, self.top_k)
        elif self.strategy == "vizinhos":
            hits = self._search(question, self.top_k)
            ids = sorted({n for h in hits[: self.expand_top] for n in neighbor_ids(h["chunk_id"])}
                         - {h["chunk_id"] for h in hits})
            found = self._search(question, len(ids), {"chunk_id": ids}, query_type="ann") if ids else []
            hits = with_neighbors(hits, {h["chunk_id"]: h for h in found}, self.expand_top)
        else:
            hits = self._search(question, self.top_k)
        return [
            Document(
                id=h["chunk_id"],
                page_content=h["text"],
                metadata={"chapter": h["chapter"], "page_start": h["page_start"],
                          "page_end": h.get("page_end", h["page_start"]), "score": h.get("score")},
            )
            for h in hits
        ]

    @mlflow.trace(span_type=SpanType.LLM)
    def generate(self, question: str, docs: list[Document]) -> str:
        hits = [{"chunk_id": d.id, "chapter": d.metadata["chapter"],
                 "page_start": d.metadata["page_start"], "text": d.page_content} for d in docs]
        resp = self.client.predict(
            endpoint=self.llm_endpoint,
            inputs={
                "messages": build_messages(question, hits, self.prompt_version),
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        )
        return resp["choices"][0]["message"]["content"]

    @mlflow.trace(span_type=SpanType.CHAIN)
    def answer(self, question: str) -> str:
        self.last_docs = self.retrieve(question)
        return self.generate(question, self.last_docs)


class ClosedBookLLM:
    """Linha de base: o mesmo LLM respondendo só de memória, sem busca nenhuma."""

    def __init__(self, llm_endpoint: str, temperature: float = 0.0, max_tokens: int = 300):
        self.llm_endpoint = llm_endpoint
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = get_deploy_client("databricks")

    @mlflow.trace(span_type=SpanType.LLM)
    def answer(self, question: str) -> str:
        resp = self.client.predict(
            endpoint=self.llm_endpoint,
            inputs={
                "messages": [{"role": "system", "content": CLOSED_BOOK_PROMPT},
                             {"role": "user", "content": question}],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        )
        return resp["choices"][0]["message"]["content"]
