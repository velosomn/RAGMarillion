"""Cadeia RAG instrumentada com MLflow Tracing."""
from __future__ import annotations

import mlflow
from mlflow.entities import Document, SpanType
from mlflow.deployments import get_deploy_client

from src.retrieval import build_messages, parse_search_result

COLUMNS = ["chunk_id", "chapter", "page_start", "text"]


class RAGMarillion:
    def __init__(self, index, llm_endpoint: str, top_k: int = 5, query_type: str = "hybrid",
                 temperature: float = 0.0, max_tokens: int = 500):
        self.index = index
        self.llm_endpoint = llm_endpoint
        self.top_k = top_k
        self.query_type = query_type
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = get_deploy_client("databricks")
        self.last_docs: list[Document] = []  # chunks usados na última chamada de answer()

    @mlflow.trace(span_type=SpanType.RETRIEVER)
    def retrieve(self, question: str) -> list[Document]:
        res = self.index.similarity_search(
            query_text=question,
            columns=COLUMNS,
            num_results=self.top_k,
            query_type=self.query_type,
            disable_notice=True,
        )
        return [
            Document(
                id=h["chunk_id"],
                page_content=h["text"],
                metadata={"chapter": h["chapter"], "page_start": h["page_start"], "score": h.get("score")},
            )
            for h in parse_search_result(res)
        ]

    @mlflow.trace(span_type=SpanType.LLM)
    def generate(self, question: str, docs: list[Document]) -> str:
        hits = [{"chunk_id": d.id, "chapter": d.metadata["chapter"],
                 "page_start": d.metadata["page_start"], "text": d.page_content} for d in docs]
        resp = self.client.predict(
            endpoint=self.llm_endpoint,
            inputs={
                "messages": build_messages(question, hits),
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        )
        return resp["choices"][0]["message"]["content"]

    @mlflow.trace(span_type=SpanType.CHAIN)
    def answer(self, question: str) -> str:
        self.last_docs = self.retrieve(question)
        return self.generate(question, self.last_docs)
