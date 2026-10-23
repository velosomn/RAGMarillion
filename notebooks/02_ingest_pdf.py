# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Ingestão do PDF
# MAGIC Extrai o texto página a página e grava na tabela `pages`.
# MAGIC
# MAGIC **Antes de seguir**, use as células de inspeção para descobrir:
# MAGIC 1. quais linhas são ruído (cabeçalho corrente, número de página) → `DROP_LINE_PATTERNS`
# MAGIC 2. como os títulos de capítulo aparecem → `CHAPTER_REGEX` no `00_config`
# MAGIC
# MAGIC ⚠️ As saídas deste notebook mostram texto do livro. Não commite outputs (use o formato `.py`, que não guarda saída).

# COMMAND ----------

# MAGIC %pip install -q pypdf
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys
sys.path.append(os.path.abspath(".."))
from pypdf import PdfReader
from src.chunking import clean_page

reader = PdfReader(PDF_PATH)
raw_pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
print(f"{len(raw_pages)} páginas")
print("Páginas sem texto:", sum(1 for _, t in raw_pages if not t.strip()), "(se forem muitas, o PDF é escaneado e precisa de OCR)")

# COMMAND ----------

# Inspeção: veja algumas páginas cruas para achar padrões de ruído e de título
for n in [10, 11, 50]:
    if n <= len(raw_pages):
        print(f"===== página {n} =====\n{raw_pages[n-1][1][:1500]}\n")

# COMMAND ----------

# Ajuste depois da inspeção. Padrão: remove linhas que são só número.
DROP_LINE_PATTERNS = [
    r"^\s*\d{1,4}\s*$",          # número de página isolado
    # r"^\s*O SILMARILLION\s*$",  # exemplo de cabeçalho corrente
]

pages = [(n, clean_page(t, DROP_LINE_PATTERNS)) for n, t in raw_pages]

# COMMAND ----------

# Descobrir títulos de capítulo: linhas curtas que começam com padrões típicos
import re
candidates = re.compile(r"^(Capítulo|CAPÍTULO|Chapter|Of |Do |Da |Dos |Das |De )")
seen = []
for n, t in pages:
    for line in t.splitlines():
        if candidates.match(line) and len(line.split()) <= 12:
            seen.append((n, line))
for n, line in seen[:60]:
    print(n, "|", line)

# COMMAND ----------

from pyspark.sql import Row

df = spark.createDataFrame([Row(page=n, text=t) for n, t in pages])
df.write.mode("overwrite").saveAsTable(PAGES_TABLE)
print(f"Gravado em {PAGES_TABLE}: {df.count()} páginas")
