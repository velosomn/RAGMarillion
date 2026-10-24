# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02 · Ingestão do PDF
# MAGIC Extrai o texto página a página e grava na tabela `pages`.
# MAGIC
# MAGIC **Antes de seguir**, use as células de inspeção para descobrir:
# MAGIC 1. quais linhas são ruído (cabeçalho corrente, número de página) → `DROP_LINE_PATTERNS`
# MAGIC 2. como os títulos de capítulo aparecem → `CHAPTER_REGEX` no `00_config`
# MAGIC
# MAGIC Para ajustar esses dois por tentativa e erro, use o modo de teste (`PAGE_RANGE` no `00_config`).
# MAGIC As verificações no fim do notebook impedem gravar uma extração ruim.
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
from src import checks
from src.chunking import clean_page

if not os.path.exists(PDF_PATH):
    vol_dir = os.path.dirname(PDF_PATH)
    files = os.listdir(vol_dir) if os.path.isdir(vol_dir) else []
    raise FileNotFoundError(
        f"PDF não encontrado em {PDF_PATH}. Arquivos no Volume: {files or 'nenhum'}. "
        f"Suba o PDF ou ajuste PDF_FILENAME no 00_config."
    )

reader = PdfReader(PDF_PATH)
n_total = len(reader.pages)
if PAGE_RANGE:
    start, end = PAGE_RANGE
    if not 1 <= start <= end <= n_total:
        raise ValueError(f"PAGE_RANGE={PAGE_RANGE} fora do PDF, que tem {n_total} páginas.")
    page_numbers = range(start, end + 1)
else:
    page_numbers = range(1, n_total + 1)

raw_pages = [(n, reader.pages[n - 1].extract_text() or "") for n in page_numbers]
print(f"{len(raw_pages)} de {n_total} páginas lidas")

# COMMAND ----------

# Inspeção: veja algumas páginas cruas para achar padrões de ruído e de título
for n, text in [raw_pages[len(raw_pages) * k // 4] for k in (1, 2, 3)]:
    print(f"===== página {n} =====\n{text[:1500]}\n")

# COMMAND ----------

# Ajuste depois da inspeção. Padrão: remove linhas que são só número.
# A verificação "Linhas repetidas" no fim do notebook sugere padrões prontos.
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

# MAGIC %md
# MAGIC ### Verificações
# MAGIC Se alguma der **ERRO**, a tabela não é gravada. **AVISO** só pede que você confira.

# COMMAND ----------

rep = checks.Report("02 · Ingestão")
rep.add("Páginas sem texto", checks.empty_pages(raw_pages, MAX_EMPTY_PAGE_FRAC))
if TEST_MODE:
    rep.info("Total de palavras", f"{checks.count_words(pages):,} (modo de teste: sem mínimo)")
else:
    rep.add("Total de palavras", checks.total_words(pages, MIN_TOTAL_WORDS))
rep.add("Termos-âncora", checks.anchor_terms(pages, ANCHOR_TERMS, MIN_ANCHOR_FRAC), level=BOOK_LEVEL)
rep.add("Caracteres corrompidos", checks.bad_chars(pages, MAX_BAD_CHAR_FRAC), level="AVISO")
rep.add("Linhas repetidas (cabeçalho/rodapé)", checks.repeated_lines(pages, REPEATED_LINE_MIN_FRAC), level="AVISO")
rep.finish()

# COMMAND ----------

from pyspark.sql import Row

df = spark.createDataFrame([Row(page=n, text=t) for n, t in pages])
df.write.mode("overwrite").saveAsTable(PAGES_TABLE)
print(f"Gravado em {PAGES_TABLE}: {df.count()} páginas")