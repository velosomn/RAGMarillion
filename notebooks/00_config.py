# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Configuração
# MAGIC Todos os outros notebooks fazem `%run ./00_config`. Ajuste aqui, não no código.

# COMMAND ----------

# --- Unity Catalog -----------------------------------------------------------
# No Free Edition o catálogo padrão se chama `workspace`.
CATALOG = "workspace"
SCHEMA = "silmarillion_rag"
VOLUME = "raw"

PDF_FILENAME = "silmarillion.pdf"  # nome do arquivo que você subir no Volume
PDF_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{PDF_FILENAME}"

PAGES_TABLE = f"{CATALOG}.{SCHEMA}.pages"
CHUNKS_TABLE = f"{CATALOG}.{SCHEMA}.chunks"

# --- Vector Search -----------------------------------------------------------
# O Free Edition permite 1 endpoint de Vector Search.
VS_ENDPOINT = "silmarillion-vs"
VS_INDEX = f"{CATALOG}.{SCHEMA}.chunks_index"

# --- Modelos (confira os nomes em Serving > Endpoints no seu workspace) ------
# Qwen3-Embedding é multilíngue: bom se o seu PDF for em português.
# Se o PDF for em inglês, `databricks-gte-large-en` também funciona.
EMBEDDING_ENDPOINT = "databricks-qwen3-embedding-0-6b"
LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

# --- Chunking ----------------------------------------------------------------
CHUNK_SIZE_WORDS = 350
CHUNK_OVERLAP_WORDS = 60
# Regex que reconhece títulos de capítulo no SEU PDF (veja o notebook 02).
# Deixe None até inspecionar o texto.
CHAPTER_REGEX = None
PREPEND_CHAPTER = True  # injeta o título do capítulo no texto do chunk

# --- Recuperação -------------------------------------------------------------
TOP_K = 5
QUERY_TYPE = "hybrid"  # "ann" (só vetorial) ou "hybrid" (vetorial + palavra-chave)

# --- Avaliação ---------------------------------------------------------------
EVAL_FILE = "../data/eval_questions.jsonl"  # caminho relativo à pasta notebooks/
# None = juiz padrão hospedado pela Databricks. Se não estiver disponível no
# Free Edition, use um endpoint do workspace, ex.: "databricks:/databricks-meta-llama-3-3-70b-instruct"
JUDGE_MODEL = None
REFUSAL_TEXT = "Não encontrei isso nos trechos recuperados"

# --- MLflow ------------------------------------------------------------------
CURRENT_USER = spark.sql("SELECT current_user()").first()[0]
MLFLOW_EXPERIMENT = f"/Users/{CURRENT_USER}/silmarillion-rag"

print(f"PDF: {PDF_PATH}\nChunks: {CHUNKS_TABLE}\nÍndice: {VS_INDEX}\nExperimento: {MLFLOW_EXPERIMENT}")
