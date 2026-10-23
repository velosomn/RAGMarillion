# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Chunking
# MAGIC Quebra as páginas em chunks que não atravessam capítulos e grava na tabela `chunks`
# MAGIC com **Change Data Feed** habilitado (exigência do índice Delta Sync).
# MAGIC
# MAGIC Títulos são detectados **linha a linha** pelo `CHAPTER_REGEX`. Um título igual ao do
# MAGIC capítulo atual (cabeçalho corrente com o nome do capítulo) é ignorado.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys
sys.path.append(os.path.abspath(".."))
import pandas as pd
from src import checks
from src.chunking import chunk_pages, find_headings

pages = [(r.page, r.text) for r in spark.table(PAGES_TABLE).orderBy("page").collect()]

chunks = chunk_pages(
    pages,
    chunk_size_words=CHUNK_SIZE_WORDS,
    overlap_words=CHUNK_OVERLAP_WORDS,
    chapter_regex=CHAPTER_REGEX,
    prepend_chapter=PREPEND_CHAPTER,
)
headings = find_headings(pages, CHAPTER_REGEX)
print(f"{len(chunks)} chunks; {sum(not h['repeat'] for h in headings)} títulos detectados")

# COMMAND ----------

# Títulos detectados (repeat=True foi ignorado como cabeçalho corrente)
if headings:
    display(pd.DataFrame(headings))

# COMMAND ----------

cdf = pd.DataFrame([c.to_dict() for c in chunks])
display(cdf.groupby("chapter", sort=False).agg(n_chunks=("chunk_id", "count"), palavras=("n_words", "sum")).reset_index())

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verificações
# MAGIC Se alguma der **ERRO**, a tabela não é gravada.

# COMMAND ----------

rep = checks.Report("03 · Chunking")
if CHAPTER_REGEX is None:
    rep.add("CHAPTER_REGEX definido",
            checks.Result(False, "None: todos os chunks ficam em 'Início'. Veja o notebook 02."), level="AVISO")
else:
    if TEST_MODE:
        rep.info("Número de capítulos", f"{sum(not h['repeat'] for h in headings)} (modo de teste: sem faixa esperada)")
    else:
        rep.add("Número de capítulos", checks.chapter_count(headings, EXPECTED_CHAPTERS))
        rep.add("Capítulo dominante", checks.dominant_chapter(chunks, MAX_CHAPTER_SHARE), level="AVISO")
    rep.add("Títulos duplicados", checks.duplicate_headings(headings))
    rep.add("Linhas longas que batem no regex", checks.long_heading_lines(pages, CHAPTER_REGEX), level="AVISO")
    rep.add("Capítulos pequenos", checks.small_chapters(chunks, MIN_CHUNKS_PER_CHAPTER), level="AVISO")
rep.add("Chunks curtos", checks.short_chunks(chunks, MIN_CHUNK_WORDS, MAX_SHORT_CHUNK_FRAC), level="AVISO")
rep.add("Cobertura de palavras",
        checks.word_coverage(pages, chunks, CHAPTER_REGEX, CHUNK_OVERLAP_WORDS, MAX_LOST_WORD_FRAC))
rep.finish()

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
