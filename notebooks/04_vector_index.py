# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Índice de Vector Search
# MAGIC Cria um índice **Delta Sync** com embeddings calculados pela Databricks a partir da coluna `text`.
# MAGIC (O Free Edition não suporta Direct Vector Access, então é Delta Sync mesmo.)

# COMMAND ----------

# MAGIC %pip install -q databricks-vectorsearch
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient(disable_notice=True)
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

# Teste rápido: compare busca vetorial pura vs híbrida num nome próprio
import os, sys
sys.path.append(os.path.abspath(".."))
from src.retrieval import parse_search_result

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
