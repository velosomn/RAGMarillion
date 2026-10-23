# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Teste contrafactual
# MAGIC O LLM já conhece o Silmarillion, então acertar não prova que ele **usou** o contexto.
# MAGIC Aqui trocamos um fato nos chunks (ex.: quem forjou as Silmarils) e verificamos se a resposta
# MAGIC segue o contexto adulterado ou a memória do modelo.
# MAGIC
# MAGIC O notebook restaura os chunks originais no final. Se ele parar no meio, rode o `03` de novo.

# COMMAND ----------

# MAGIC %pip install -q databricks-vectorsearch "mlflow[databricks]>=3.1"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys, time
sys.path.append(os.path.abspath(".."))
import mlflow
from databricks.vector_search.client import VectorSearchClient
from src.rag import SilmarillionRAG

mlflow.set_experiment(MLFLOW_EXPERIMENT)
index = VectorSearchClient(disable_notice=True).get_index(VS_ENDPOINT, VS_INDEX)
rag = SilmarillionRAG(index, LLM_ENDPOINT, top_k=TOP_K, query_type=QUERY_TYPE)

QUESTION = "Quem forjou as Silmarils?"
TRUE_FACT, FAKE_FACT = "Fëanor", "Maglor"  # troque à vontade


def sync_and_wait(timeout_s: int = 900) -> None:
    index.sync()
    start = time.time()
    while time.time() - start < timeout_s:
        state = index.describe().get("status", {}).get("detailed_state", "")
        print("estado do índice:", state)
        if state == "ONLINE_NO_PENDING_UPDATE":
            return
        time.sleep(20)
    raise TimeoutError("Sync demorou demais")

# COMMAND ----------

docs = rag.retrieve(QUESTION)
target_ids = [d.id for d in docs if TRUE_FACT in d.page_content]
print("Chunks que serão adulterados:", target_ids)
assert target_ids, f"Nenhum chunk recuperado contém '{TRUE_FACT}'. Ajuste a pergunta."

ids_sql = ", ".join(f"'{i}'" for i in target_ids)
backup = spark.table(CHUNKS_TABLE).where(f"chunk_id IN ({ids_sql})").toPandas()

before = rag.answer(QUESTION)
print("ANTES:", before)

# COMMAND ----------

spark.sql(f"""
  UPDATE {CHUNKS_TABLE}
  SET text = replace(text, '{TRUE_FACT}', '{FAKE_FACT}')
  WHERE chunk_id IN ({ids_sql})
""")
sync_and_wait()

after = rag.answer(QUESTION)
print("DEPOIS:", after)

follows_context = FAKE_FACT.lower() in after.lower()
with mlflow.start_run(run_name=f"counterfactual_{TRUE_FACT}_to_{FAKE_FACT}"):
    mlflow.log_params({"question": QUESTION, "true": TRUE_FACT, "fake": FAKE_FACT, "llm": LLM_ENDPOINT})
    mlflow.log_metric("follows_context", float(follows_context))
print("Seguiu o contexto adulterado?" , follows_context)

# COMMAND ----------

# Restaura os chunks originais
spark.createDataFrame(backup).createOrReplaceTempView("chunks_backup")
spark.sql(f"""
  MERGE INTO {CHUNKS_TABLE} t
  USING chunks_backup b ON t.chunk_id = b.chunk_id
  WHEN MATCHED THEN UPDATE SET t.text = b.text
""")
sync_and_wait()
print("Chunks restaurados.")

# COMMAND ----------

# MAGIC %md
# MAGIC **Para explorar:** repita trocando `LLM_ENDPOINT` por um modelo menor, ou deixando o prompt
# MAGIC sem a regra "use SOMENTE os trechos" (em `src/retrieval.py`). Modelos grandes tendem a
# MAGIC "corrigir" o contexto com o que lembram; isso é exatamente o que você quer medir.
