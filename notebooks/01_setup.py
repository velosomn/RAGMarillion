# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Setup do ambiente
# MAGIC Cria schema, Volume e o endpoint de Vector Search. Rode **uma vez**.
# MAGIC
# MAGIC Depois de rodar, suba o PDF em **Catalog > workspace > ragmarillion > raw > Upload to this volume**.

# COMMAND ----------

# MAGIC %pip install -q databricks-vectorsearch
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys
sys.path.append(os.path.abspath(".."))
from src.retrieval import wait_for_endpoint

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")
print("Schema e Volume prontos.")

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient(disable_notice=True)
existing = [e["name"] for e in vsc.list_endpoints().get("endpoints", [])]

if VS_ENDPOINT in existing:
    print(f"Endpoint {VS_ENDPOINT} já existe.")
elif existing:
    # Free Edition: só 1 endpoint. Reaproveite o que existe.
    raise RuntimeError(
        f"Já existe o endpoint {existing}. No Free Edition só cabe um: "
        f"ajuste VS_ENDPOINT no 00_config para esse nome."
    )
else:
    vsc.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")

wait_for_endpoint(vsc, VS_ENDPOINT)  # pode levar ~10-15 min na primeira vez

# COMMAND ----------

# MAGIC %md
# MAGIC ### Checagem dos modelos
# MAGIC Confere se os endpoints de embedding e LLM do `00_config` existem no seu workspace.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
available = {e.name for e in w.serving_endpoints.list()}
for name in [EMBEDDING_ENDPOINT, LLM_ENDPOINT]:
    print(("OK      " if name in available else "FALTANDO"), name)

print("\nEndpoints disponíveis com 'embed' no nome:", sorted(n for n in available if "embed" in n or "gte" in n or "bge" in n))
