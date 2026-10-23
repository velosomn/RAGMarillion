# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Índice de Vector Search
# MAGIC Cria um índice **Delta Sync** com embeddings calculados pela Databricks a partir da coluna `text`.
# MAGIC (O Free Edition não suporta Direct Vector Access, então é Delta Sync mesmo.)

# COMMAND ----------

# MAGIC %pip install -q "databricks-ai-search>=0.80,<1.0"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys
sys.path.append(os.path.abspath(".."))
from databricks.ai_search.client import AISearchClient
from src import checks
from src.retrieval import indexed_row_count, parse_search_result, wait_until

vsc = AISearchClient(disable_notice=True)
existing = [i["name"] for i in vsc.list_indexes(VS_ENDPOINT).get("vector_indexes", [])]

if VS_INDEX in existing:
    index = vsc.get_index(VS_ENDPOINT, VS_INDEX)
    print("Índice já existe, disparando sync...")
    index.sync()
else:
    index = vsc.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        index_name=VS_INDEX,
        source_table_name=CHUNKS_TABLE,
        pipeline_type="TRIGGERED",
        primary_key="chunk_id",
        embedding_source_column="text",
        embedding_model_endpoint_name=EMBEDDING_ENDPOINT,
    )

index.wait_until_ready(verbose=True)

# COMMAND ----------

# MAGIC %md
# MAGIC > Trocou o modelo de embedding? Apague o índice (`vsc.delete_index(VS_ENDPOINT, VS_INDEX)`) e recrie.
# MAGIC > Mudou só os chunks? Basta `index.sync()`.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verificações
# MAGIC 1. O índice tem o mesmo número de linhas que a tabela de chunks.
# MAGIC 2. **Auto-recuperação:** buscar um trecho do meio de um chunk precisa devolver esse mesmo chunk.
# MAGIC    Pega índice desatualizado (o texto mudou e o sync não terminou) ou modelo de embedding errado.

# COMMAND ----------

from pyspark.sql import functions as F

n_chunks = spark.table(CHUNKS_TABLE).count()
wait_until(lambda: indexed_row_count(index) == n_chunks, timeout_s=SYNC_TIMEOUT_S, what="o índice ter todas as linhas")

sample = (spark.table(CHUNKS_TABLE).orderBy(F.rand(seed=42)).limit(SMOKE_SAMPLES)
          .select("chunk_id", "text").collect())
hits = []
for r in sample:
    words = r.text.split()
    mid = len(words) // 2
    res = index.similarity_search(query_text=" ".join(words[mid:mid + 15]), columns=["chunk_id"],
                                  num_results=5, query_type="hybrid")
    hits.append((r.chunk_id, [h["chunk_id"] for h in parse_search_result(res)]))

rep = checks.Report("04 · Índice")
rep.add("Linhas no índice", checks.index_rows(indexed_row_count(index), n_chunks))
rep.add("Auto-recuperação", checks.self_retrieval(hits))
rep.finish()

# COMMAND ----------

# Teste rápido: compare busca vetorial pura vs híbrida num nome próprio
q = "Quem forjou as Silmarils?"
for qt in ["ann", "hybrid"]:
    res = index.similarity_search(
        query_text=q,
        columns=["chunk_id", "chapter", "page_start", "text"],
        num_results=3,
        query_type=qt,
    )
    print(f"--- {qt} ---")
    for h in parse_search_result(res):
        print(h["chunk_id"], h["chapter"], round(h["score"], 4))
