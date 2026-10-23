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
from src.rag import RAGMarillion
from src.retrieval import hit_at_k, reciprocal_rank

mlflow.set_experiment(MLFLOW_EXPERIMENT)
index = VectorSearchClient(disable_notice=True).get_index(VS_ENDPOINT, VS_INDEX)

with open(os.path.abspath(EVAL_FILE), encoding="utf-8") as f:
    eval_set = [json.loads(line) for line in f if line.strip()]
print(f"{len(eval_set)} perguntas:", pd.Series([e["category"] for e in eval_set]).value_counts().to_dict())

# COMMAND ----------

def judges():
    if JUDGE_MODEL:
        return [Correctness(model=JUDGE_MODEL), RetrievalGroundedness(model=JUDGE_MODEL)]
    return [Correctness(), RetrievalGroundedness()]


def run_config(name: str, top_k: int, query_type: str) -> pd.DataFrame:
    rag = RAGMarillion(index, LLM_ENDPOINT, top_k=top_k, query_type=query_type)
    rows = []
    with mlflow.start_run(run_name=name):
        mlflow.log_params({
            "top_k": top_k, "query_type": query_type, "embedding": EMBEDDING_ENDPOINT,
            "llm": LLM_ENDPOINT, "chunk_size": CHUNK_SIZE_WORDS, "overlap": CHUNK_OVERLAP_WORDS,
            "prepend_chapter": PREPEND_CHAPTER,
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
