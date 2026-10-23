# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Teste contrafactual
# MAGIC O LLM já conhece o Silmarillion, então acertar não prova que ele **usou** o contexto.
# MAGIC Aqui trocamos um fato nos chunks (ex.: quem forjou as Silmarils) e verificamos se a resposta
# MAGIC segue o contexto adulterado ou a memória do modelo.
# MAGIC
# MAGIC A troca e a restauração ficam na mesma célula (`try/finally`): mesmo que algo falhe no meio,
# MAGIC os chunks originais voltam. Se o notebook for interrompido à força, rode o `03` e o `04` de novo.

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
from pyspark.sql import functions as F
from src import checks
from src.rag import RAGMarillion
from src.retrieval import parse_search_result, wait_until

mlflow.set_experiment(MLFLOW_EXPERIMENT)
index = VectorSearchClient(disable_notice=True).get_index(VS_ENDPOINT, VS_INDEX)
rag = RAGMarillion(index, LLM_ENDPOINT, top_k=TOP_K, query_type=QUERY_TYPE)

QUESTION = "Quem forjou as Silmarils?"
# O fato falso não pode aparecer no contexto original: senão a resposta poderia citá-lo
# por outro motivo (ex.: "Maglor" é filho de Fëanor). A verificação abaixo confere.
TRUE_FACT, FAKE_FACT = "Fëanor", "Eöl"


def index_texts(ids: list[str]) -> dict[str, str]:
    """Texto atual dos chunks `ids` no índice (não na tabela)."""
    res = index.similarity_search(query_text=QUESTION, columns=["chunk_id", "text"],
                                  filters={"chunk_id": ids}, num_results=len(ids))
    return {h["chunk_id"]: h["text"] for h in parse_search_result(res)}


def index_shows(ids: list[str], present: str, absent: str) -> bool:
    texts = index_texts(ids)
    return len(texts) == len(ids) and all(present in t and absent not in t for t in texts.values())

# COMMAND ----------

docs = rag.retrieve(QUESTION)
target_ids = [d.id for d in docs if TRUE_FACT in d.page_content]
fake_in_context = [d.id for d in docs if FAKE_FACT.lower() in d.page_content.lower()]

rep = checks.Report("07 · Antes da troca")
rep.add(f"Contexto contém '{TRUE_FACT}'", checks.Result(
    bool(target_ids),
    f"chunks que serão adulterados: {target_ids}" if target_ids else
    "nenhum chunk recuperado contém o fato. Ajuste a pergunta ou, no modo de teste, use um "
    "PAGE_RANGE que inclua a criação das Silmarils."))
rep.add(f"Contexto não contém '{FAKE_FACT}'", checks.Result(
    not fake_in_context,
    "ok" if not fake_in_context else f"já aparece em {fake_in_context}; escolha outro FAKE_FACT"))
rep.finish()

ids_sql = ", ".join(f"'{i}'" for i in target_ids)
backup = spark.table(CHUNKS_TABLE).where(f"chunk_id IN ({ids_sql})").toPandas()

before = rag.answer(QUESTION)
print("ANTES:", before)

# COMMAND ----------

def restore() -> checks.Report:
    spark.createDataFrame(backup).createOrReplaceTempView("chunks_backup")
    spark.sql(f"""
      MERGE INTO {CHUNKS_TABLE} t
      USING chunks_backup b ON t.chunk_id = b.chunk_id
      WHEN MATCHED THEN UPDATE SET t.text = b.text
    """)
    index.sync()
    index_ok = wait_until(lambda: index_shows(target_ids, TRUE_FACT, FAKE_FACT),
                          timeout_s=SYNC_TIMEOUT_S, what="o índice voltar ao texto original")
    leftover = (spark.table(CHUNKS_TABLE).where(f"chunk_id IN ({ids_sql})")
                .where(F.col("text").contains(FAKE_FACT)).count())
    r = checks.Report("07 · Restauração")
    r.add("Tabela sem o fato falso", checks.Result(leftover == 0, f"{leftover} chunk(s) ainda com '{FAKE_FACT}'"))
    r.add("Índice sem o fato falso", checks.Result(index_ok, "ok" if index_ok else
                                                   f"não voltou em {SYNC_TIMEOUT_S}s; rode index.sync() de novo"))
    return r


after, used_ids = None, []
try:
    spark.sql(f"""
      UPDATE {CHUNKS_TABLE}
      SET text = replace(text, '{TRUE_FACT}', '{FAKE_FACT}')
      WHERE chunk_id IN ({ids_sql})
    """)
    index.sync()
    # Espera o índice mostrar o texto adulterado: o estado do sync logo depois de
    # index.sync() ainda pode ser o antigo, e a pergunta seria feita sobre o índice velho.
    if not wait_until(lambda: index_shows(target_ids, FAKE_FACT, TRUE_FACT),
                      timeout_s=SYNC_TIMEOUT_S, what="o índice mostrar o fato adulterado"):
        raise TimeoutError("O índice não refletiu a troca a tempo; o teste não foi feito.")
    after = rag.answer(QUESTION)
    used_ids = [d.id for d in rag.last_docs]
    print("DEPOIS:", after)
finally:
    restore().finish()

# COMMAND ----------

mentions_fake = FAKE_FACT.lower() in after.lower()
mentions_true = TRUE_FACT.lower() in after.lower()
follows_context = mentions_fake and not mentions_true
adulterated_used = sorted(set(used_ids) & set(target_ids))

rep = checks.Report("07 · Resultado")
rep.add("Chunks adulterados foram recuperados", checks.Result(
    bool(adulterated_used),
    f"{adulterated_used}" if adulterated_used else "nenhum: o modelo não viu o contexto falso, resultado inconclusivo"),
    level="AVISO")
rep.finish()

with mlflow.start_run(run_name=f"counterfactual_{TRUE_FACT}_to_{FAKE_FACT}"):
    mlflow.set_tags(MODE_TAGS)
    mlflow.log_params({"question": QUESTION, "true": TRUE_FACT, "fake": FAKE_FACT, "llm": LLM_ENDPOINT})
    mlflow.log_metrics({
        "follows_context": float(follows_context),
        "mentions_fake": float(mentions_fake),
        "mentions_true": float(mentions_true),
        "adulterated_chunks_retrieved": float(len(adulterated_used)),
    })
print(f"Cita '{FAKE_FACT}': {mentions_fake} | cita '{TRUE_FACT}': {mentions_true} | seguiu o contexto: {follows_context}")

# COMMAND ----------

# MAGIC %md
# MAGIC **Como ler:** `follows_context=1` exige citar o fato falso **e não** citar o verdadeiro.
# MAGIC Citar os dois ("o texto diz Eöl, mas foi Fëanor") é o modelo corrigindo o contexto com a memória.
# MAGIC
# MAGIC **Para explorar:** repita trocando `LLM_ENDPOINT` por um modelo menor, ou deixando o prompt
# MAGIC sem a regra "use SOMENTE os trechos" (em `src/retrieval.py`). Modelos grandes tendem a
# MAGIC "corrigir" o contexto com o que lembram; isso é exatamente o que você quer medir.
