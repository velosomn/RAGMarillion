# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 00 · Configuração
# MAGIC Todos os outros notebooks fazem `%run ./00_config`. Ajuste aqui, não no código.

# COMMAND ----------

# --- Unity Catalog -----------------------------------------------------------
# No Free Edition o catálogo padrão se chama `workspace`.
CATALOG = "workspace"
SCHEMA = "ragmarillion"
VOLUME = "raw"

PDF_FILENAME = "O Silmarillion - J.R.R. Tolkien.pdf"  # nome do arquivo que você subir no Volume
PDF_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{PDF_FILENAME}"

# --- Modo de teste -----------------------------------------------------------
# None = livro inteiro. (início, fim) = só essas páginas do PDF, inclusive.
# Escolha um trecho que atravesse a passagem entre dois capítulos: é o que testa o
# CHAPTER_REGEX e os cabeçalhos. Tabelas e índice ganham o sufixo _teste, para não
# sobrescrever os do livro inteiro.
PAGE_RANGE = (153,176)
TEST_MODE = PAGE_RANGE is not None
_SUFFIX = "_teste" if TEST_MODE else ""
MODE_TAGS = {"modo": "teste" if TEST_MODE else "completo", "paginas": str(PAGE_RANGE or "todas")}

PAGES_TABLE = f"{CATALOG}.{SCHEMA}.pages{_SUFFIX}"
CHUNKS_TABLE = f"{CATALOG}.{SCHEMA}.chunks{_SUFFIX}"

# --- Vector Search -----------------------------------------------------------
# O Free Edition permite 1 endpoint de Vector Search (com vários índices).
VS_ENDPOINT = "ragmarillion-vs"
VS_INDEX = f"{CATALOG}.{SCHEMA}.chunks_index{_SUFFIX}"
SYNC_TIMEOUT_S = 900

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
CHAPTER_REGEX = r"^CAP[IÍ]TULO [IVXLC]+\b"
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

# --- Verificações ------------------------------------------------------------
# ERRO para o notebook; AVISO só registra. Checagens que só fazem sentido no livro
# inteiro (total de palavras, termos-âncora...) viram AVISO no modo de teste.
BOOK_LEVEL = "AVISO" if TEST_MODE else "ERRO"

# 02 · Ingestão
MAX_EMPTY_PAGE_FRAC = 0.10      # acima disso o PDF provavelmente é escaneado
MIN_TOTAL_WORDS = 80_000        # o livro tem bem mais que isso
ANCHOR_TERMS = ["Fëanor", "Silmaril", "Morgoth", "Valinor", "Beleriand", "Lúthien", "Túrin", "Gondolin"]
MIN_ANCHOR_FRAC = 0.75          # fração dos termos-âncora que precisa aparecer
MAX_BAD_CHAR_FRAC = 0.0001      # caracteres corrompidos (�, ﬁ, 'F¨eanor')
REPEATED_LINE_MIN_FRAC = 0.2    # linha de topo/rodapé em ≥20% das páginas = cabeçalho

# 03 · Chunking
EXPECTED_CHAPTERS = (20, 35)    # Ainulindalë, Valaquenta, 24 do Quenta, Akallabêth, Anéis...
MIN_CHUNKS_PER_CHAPTER = 3
MAX_CHAPTER_SHARE = 0.4
MIN_CHUNK_WORDS = 50
MAX_SHORT_CHUNK_FRAC = 0.05
MAX_LOST_WORD_FRAC = 0.01

# 04 · Índice
SMOKE_SAMPLES = 4               # chunks buscados pelo próprio texto

# --- MLflow ------------------------------------------------------------------
CURRENT_USER = spark.sql("SELECT current_user()").first()[0]
MLFLOW_EXPERIMENT = f"/Users/{CURRENT_USER}/ragmarillion"

print(f"Modo: {MODE_TAGS['modo']} (páginas: {MODE_TAGS['paginas']})")
print(f"PDF: {PDF_PATH}\nChunks: {CHUNKS_TABLE}\nÍndice: {VS_INDEX}\nExperimento: {MLFLOW_EXPERIMENT}")