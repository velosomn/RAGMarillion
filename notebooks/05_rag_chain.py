# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Cadeia RAG
# MAGIC Recupera top-k → monta prompt com citações → chama o LLM. Tudo instrumentado com MLflow Tracing:
# MAGIC abra a aba **Traces** do experimento para ver os chunks recuperados em cada pergunta.

# COMMAND ----------

# MAGIC %pip install -q databricks-vectorsearch "mlflow[databricks]>=3.1"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys
sys.path.append(os.path.abspath(".."))
import mlflow
from databricks.vector_search.client import VectorSearchClient
from src.rag import RAGMarillion

mlflow.set_experiment(MLFLOW_EXPERIMENT)
index = VectorSearchClient(disable_notice=True).get_index(VS_ENDPOINT, VS_INDEX)
rag = RAGMarillion(index, LLM_ENDPOINT, top_k=TOP_K, query_type=QUERY_TYPE)

# COMMAND ----------

perguntas = [
    "Quem forjou as Silmarils?",
    "Quais outros nomes Túrin usou?",
    "Qual é a relação entre Lúthien e Elrond?",
    "Qual é a data de aniversário de Bilbo?",  # não está no livro: deve recusar
]
from src import checks

rep = checks.Report("05 · Cadeia RAG")
for p in perguntas:
    ans = rag.answer(p)
    print(f"Q: {p}\nA: {ans}\n")
    rep.add(f"Citações · {p}", checks.citations(ans, [d.id for d in rag.last_docs], REFUSAL_TEXT), level="AVISO")
rep.finish()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Brinque aqui
# MAGIC Compare o efeito de `query_type` e `top_k` numa pergunta difícil.

# COMMAND ----------

q = "Qual rei dos Noldor morreu na Nirnaeth Arnoediad?"
for qt in ["ann", "hybrid"]:
    rag.query_type = qt
    docs = rag.retrieve(q)
    print(qt, [(d.id, d.metadata["chapter"]) for d in docs])
rag.query_type = QUERY_TYPE
