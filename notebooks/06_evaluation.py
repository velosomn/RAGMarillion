# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Avaliação
# MAGIC Duas camadas, separadas de propósito:
# MAGIC
# MAGIC | Camada | Métrica | Por quê |
# MAGIC |---|---|---|
# MAGIC | Recuperação | hit@k, MRR (proxy por termos esperados) | O LLM já conhece o Silmarillion; uma resposta certa **não prova** que a recuperação funcionou |
# MAGIC | Geração | Correctness, RetrievalGroundedness (juízes LLM), taxa de recusa | Mede se a resposta está correta **e** apoiada nos chunks |
# MAGIC
# MAGIC Cada configuração vira um run no MLflow: compare em **Experiments > ragmarillion**.
# MAGIC Runs do modo de teste levam a tag `modo=teste`.

# COMMAND ----------

# MAGIC %pip install -q databricks-vectorsearch "mlflow[databricks]>=3.1"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys, json
sys.path.append(os.path.abspath(".."))
import mlflow
import pandas as pd
from databricks.vector_search.client import VectorSearchClient
from mlflow.genai.scorers import Correctness, RetrievalGroundedness
from src import checks
from src.rag import RAGMarillion
from src.retrieval import hit_at_k, reciprocal_rank

mlflow.set_experiment(MLFLOW_EXPERIMENT)
index = VectorSearchClient(disable_notice=True).get_index(VS_ENDPOINT, VS_INDEX)

with open(os.path.abspath(EVAL_FILE), encoding="utf-8") as f:
    eval_set = [json.loads(line) for line in f if line.strip()]
print(f"{len(eval_set)} perguntas:", pd.Series([e["category"] for e in eval_set]).value_counts().to_dict())


def judges():
    if JUDGE_MODEL:
        return [Correctness(model=JUDGE_MODEL), RetrievalGroundedness(model=JUDGE_MODEL)]
    return [Correctness(), RetrievalGroundedness()]

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verificações
# MAGIC - O gabarito está bem formado.
# MAGIC - Os `expected_terms` existem no texto. Se a sua edição grafa um nome de outro jeito, o hit@k
# MAGIC   daria zero para sempre e pareceria culpa da recuperação. No modo de teste, as perguntas
# MAGIC   sobre partes fora do trecho carregado são deixadas de fora.
# MAGIC - O juiz LLM responde, testado com um exemplo antes de rodar a ablação inteira.

# COMMAND ----------

rep = checks.Report("06 · Avaliação")
rep.add("Gabarito bem formado", checks.validate_eval_set(eval_set))

texts = [r.text for r in spark.table(CHUNKS_TABLE).select("text").collect()]
missing = checks.missing_terms(eval_set, texts)
unreachable = checks.unreachable_questions(eval_set, missing)
if TEST_MODE:
    eval_set = [e for e in eval_set if e["id"] not in unreachable]
    n_answerable = sum(e["category"] != "unanswerable" for e in eval_set)
    rep.info("Perguntas fora do trecho", f"{len(unreachable)} deixadas de fora: {unreachable}")
    rep.add("Perguntas respondíveis no trecho",
            checks.Result(n_answerable > 0, f"{n_answerable} sobraram; escolha um PAGE_RANGE maior se for zero"))
else:
    rep.add("Perguntas com algum termo no texto",
            checks.Result(not unreachable, f"sem nenhum termo esperado no texto: {unreachable or 'nenhuma'}"))
    rep.add("Termos esperados no texto", checks.absent_terms(missing), level="AVISO")

try:
    fb = judges()[0](inputs={"question": "Quem forjou as Silmarils?"}, outputs="Fëanor.",
                     expectations={"expected_response": "Fëanor."})
    rep.add("Juiz LLM responde", checks.Result(True, f"Correctness de teste → {fb.value}"))
except Exception as e:
    rep.add("Juiz LLM responde", checks.Result(
        False, f"{type(e).__name__}: {e}. Defina JUDGE_MODEL no 00_config com um endpoint do workspace."))
rep.finish()

# COMMAND ----------

def run_config(name: str, top_k: int, query_type: str) -> pd.DataFrame:
    rag = RAGMarillion(index, LLM_ENDPOINT, top_k=top_k, query_type=query_type)
    rows = []
    with mlflow.start_run(run_name=name):
        mlflow.set_tags(MODE_TAGS)
        mlflow.log_params({
            "top_k": top_k, "query_type": query_type, "embedding": EMBEDDING_ENDPOINT,
            "llm": LLM_ENDPOINT, "chunk_size": CHUNK_SIZE_WORDS, "overlap": CHUNK_OVERLAP_WORDS,
            "prepend_chapter": PREPEND_CHAPTER, "n_questions": len(eval_set),
        })

        # 1) Recuperação + recusa (determinístico)
        for e in eval_set:
            docs = rag.retrieve(e["question"])
            hits = [{"text": d.page_content} for d in docs]
            row = {"id": e["id"], "category": e["category"]}
            if e["category"] == "unanswerable":
                ans = rag.generate(e["question"], docs)
                row["refused"] = REFUSAL_TEXT.lower() in ans.lower()
            else:
                row["hit"] = hit_at_k(hits, e["expected_terms"])
                row["rr"] = reciprocal_rank(hits, e["expected_terms"])
            rows.append(row)
        df = pd.DataFrame(rows)
        answerable = df[df.category != "unanswerable"]
        mlflow.log_metrics({
            f"hit_at_{top_k}": answerable["hit"].mean(),
            "mrr": answerable["rr"].mean(),
            "refusal_rate_unanswerable": df.loc[df.category == "unanswerable", "refused"].mean(),
        })
        for cat, g in answerable.groupby("category"):
            mlflow.log_metric(f"hit_{cat}", g["hit"].mean())

        # 2) Geração com juízes LLM (só perguntas respondíveis)
        data = [
            {"inputs": {"question": e["question"]}, "expectations": {"expected_response": e["expected_response"]}}
            for e in eval_set if e["category"] != "unanswerable"
        ]
        mlflow.genai.evaluate(data=data, predict_fn=lambda question: rag.answer(question), scorers=judges())
    return df

# COMMAND ----------

# Ablação: o experimento mínimo que vale a pena rodar
configs = [
    ("ann_k3", 3, "ann"),
    ("ann_k5", 5, "ann"),
    ("hybrid_k5", 5, "hybrid"),
]
results = {name: run_config(name, k, qt) for name, k, qt in configs}

# COMMAND ----------

summary = pd.DataFrame({
    name: {
        "hit@k": df.loc[df.category != "unanswerable", "hit"].mean(),
        "MRR": df.loc[df.category != "unanswerable", "rr"].mean(),
        "recusa (sem resposta)": df.loc[df.category == "unanswerable", "refused"].mean(),
    }
    for name, df in results.items()
}).T
display(summary)

# COMMAND ----------

# Onde errou? Perguntas sem hit em cada configuração
for name, df in results.items():
    misses = df[(df.category != "unanswerable") & (~df["hit"].astype(bool))]["id"].tolist()
    print(name, "→ sem hit:", misses)
