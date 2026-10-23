# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Chunking
# MAGIC Quebra as páginas em chunks que não atravessam capítulos e grava na tabela `chunks`
# MAGIC com **Change Data Feed** habilitado (exigência do índice Delta Sync).

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys
sys.path.append(os.path.abspath(".."))
from src.chunking import chunk_pages

pages = [(r.page, r.text) for r in spark.table(PAGES_TABLE).orderBy("page").collect()]

chunks = chunk_pages(
    pages,
    chunk_size_words=CHUNK_SIZE_WORDS,
    overlap_words=CHUNK_OVERLAP_WORDS,
    chapter_regex=CHAPTER_REGEX,
    prepend_chapter=PREPEND_CHAPTER,
)
print(f"{len(chunks)} chunks")

# COMMAND ----------

import pandas as pd

cdf = pd.DataFrame([c.to_dict() for c in chunks])
display(cdf.groupby("chapter").agg(n_chunks=("chunk_id", "count"), palavras=("n_words", "sum")).reset_index())

# COMMAND ----------

(spark.createDataFrame(cdf)
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(CHUNKS_TABLE))

spark.sql(f"ALTER TABLE {CHUNKS_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
print(f"Gravado em {CHUNKS_TABLE} com Change Data Feed habilitado.")

# COMMAND ----------

# MAGIC %md
# MAGIC **Experimento:** mude `CHUNK_SIZE_WORDS`, `CHUNK_OVERLAP_WORDS` ou `PREPEND_CHAPTER`,
# MAGIC rode este notebook de novo, depois `04` (só a célula de `sync`) e `06`. Compare no MLflow.
