# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Avaliação
# MAGIC Compara configurações do RAG e uma linha de base sem contexto, sobre o mesmo gabarito.
# MAGIC
# MAGIC | Camada | Métrica | Como é medida |
# MAGIC |---|---|---|
# MAGIC | Recuperação | Recall@k, MRR, nDCG@k, Precisão@k | Pela **página**: o trecho buscado cobre a página onde está a resposta? Vale para qualquer chunking. Só nas perguntas com `evidence_pages` (as sintéticas, do 06a) |
# MAGIC | Recuperação (aproximação) | hit@k por termos | Algum trecho contém um termo esperado? Vale para o gabarito manual, que ainda não tem páginas |
# MAGIC | Recusa | Taxa de recusa | Nas perguntas sem resposta no livro |
# MAGIC | Resposta | Correctness, RetrievalGroundedness, RetrievalSufficiency (juízes LLM) | Numa amostra de `EVAL_JUDGE_SAMPLE` perguntas, por custo |
# MAGIC
# MAGIC **Gabarito:** o manual (`data/eval_questions.jsonl`) mais o sintético (`SYNTH_TABLE`, gerado no 06a).
# MAGIC A divisão é fixa por id: compare configurações em `EVAL_SPLIT = "dev"` e use `"test"` uma vez só,
# MAGIC para confirmar a escolhida.
# MAGIC
# MAGIC **Linha de base:** o mesmo LLM respondendo de memória, sem busca (`llm_sem_contexto`). Mostra onde
# MAGIC o RAG agrega valor em vez de assumir que sempre agrega.

# COMMAND ----------

# MAGIC %pip install -q "databricks-ai-search>=0.80,<1.0" "mlflow[databricks]>=3.1"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys, json, hashlib
sys.path.append(os.path.abspath(".."))
import mlflow
import pandas as pd
from databricks.ai_search.client import AISearchClient
from mlflow.genai.scorers import Correctness, RetrievalGroundedness, RetrievalSufficiency
from src import checks
from src.rag import ClosedBookLLM, RAGMarillion
from src.retrieval import hit_at_k, page_scores, reciprocal_rank
from src.synth import split_for

mlflow.set_experiment(MLFLOW_EXPERIMENT)
index = AISearchClient(disable_notice=True).get_index(VS_ENDPOINT, VS_INDEX)

with open(os.path.abspath(EVAL_FILE), encoding="utf-8") as f:
    manual = [json.loads(line) for line in f if line.strip()]
for e in manual:
    e["split"] = split_for(e["id"])

synthetic = []
if spark.catalog.tableExists(SYNTH_TABLE):
    cols = ["id", "category", "split", "question", "expected_response", "expected_terms", "evidence_pages"]
    synthetic = [r.asDict() for r in spark.table(SYNTH_TABLE).where("status = 'ok'").select(*cols).collect()]

eval_all = manual + synthetic
eval_set = eval_all if EVAL_SPLIT == "todos" else [e for e in eval_all if e["split"] == EVAL_SPLIT]
print(f"Gabarito {EVAL_SPLIT}: {len(eval_set)} perguntas "
      f"({sum(e['category'] != 'sintetica' for e in eval_set)} manuais, {sum(e['category'] == 'sintetica' for e in eval_set)} sintéticas)")
print(pd.Series([e["category"] for e in eval_set]).value_counts().to_dict())


def judge_kwargs() -> dict:
    return {"model": JUDGE_MODEL} if JUDGE_MODEL else {}


def judges():
    return [Correctness(**judge_kwargs()), RetrievalGroundedness(**judge_kwargs()), RetrievalSufficiency(**judge_kwargs())]


def closed_book_judges():
    # Sem busca não há trechos: só dá para julgar se a resposta está correta.
    return [Correctness(**judge_kwargs())]

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verificações
# MAGIC - O gabarito está bem formado e há perguntas sintéticas (senão, rode o 06a).
# MAGIC - Os `expected_terms` existem no texto da sua edição.
# MAGIC - O juiz LLM responde, testado com um exemplo antes de rodar tudo.

# COMMAND ----------

rep = checks.Report("06 · Avaliação")
rep.add("Gabarito bem formado", checks.validate_eval_set(eval_set))
rep.add("Gabarito sintético", checks.Result(
    bool(synthetic), f"{len(synthetic)} perguntas aprovadas em {SYNTH_TABLE}" if synthetic else
    f"{SYNTH_TABLE} não existe ou está vazia: rode o 06a para ter Recall@k por página"), level="AVISO")
if EVAL_SPLIT == "test":
    rep.info("Conjunto de teste", "use uma vez só, para confirmar a configuração escolhida no dev")

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

if EVAL_JUDGE_SAMPLE:
    try:
        fb = Correctness(**judge_kwargs())(inputs={"question": "Quem forjou as Silmarils?"}, outputs="Fëanor.",
                                           expectations={"expected_response": "Fëanor."})
        rep.add("Juiz LLM responde", checks.Result(True, f"Correctness de teste → {fb.value}"))
    except Exception as e:
        rep.add("Juiz LLM responde", checks.Result(
            False, f"{type(e).__name__}: {e}. Defina JUDGE_MODEL no 00_config com um endpoint do workspace."))
else:
    rep.info("Juízes LLM", "EVAL_JUDGE_SAMPLE = 0: só as métricas de recuperação")
rep.finish()

# COMMAND ----------

def judge_sample(questions: list[dict], n: int) -> list[dict]:
    """Amostra fixa para os juízes: as manuais primeiro (as mais difíceis), depois as sintéticas."""
    answerable = [e for e in questions if e["category"] != "unanswerable"]
    order = lambda e: (e["category"] == "sintetica", hashlib.md5(e["id"].encode()).hexdigest())
    return sorted(answerable, key=order)[:n]


def as_eval_data(questions: list[dict]) -> list[dict]:
    return [{"inputs": {"question": e["question"]}, "expectations": {"expected_response": e["expected_response"]}}
            for e in questions]


def judged(result) -> dict:
    """Médias dos juízes devolvidas pelo mlflow.genai.evaluate."""
    return {k: v for k, v in (result.metrics or {}).items() if k.endswith("/mean")}


def retrieval_summary(df: pd.DataFrame) -> dict:
    answerable = df[df.category != "unanswerable"]
    m = {"hit_terms": answerable["hit"].mean(), "mrr_terms": answerable["rr_terms"].mean()}
    if "recall" in df:
        paged = answerable[answerable["recall"].notna()]
        if len(paged):
            m.update({"recall_at_k": paged["recall"].mean(), "mrr": paged["rr"].mean(),
                      "ndcg_at_k": paged["ndcg"].mean(), "precision_at_k": paged["precision"].mean(),
                      "n_with_pages": len(paged)})
    unanswerable = df[df.category == "unanswerable"]
    if len(unanswerable):
        m["refusal_rate_unanswerable"] = unanswerable["refused"].mean()
    return {k: float(v) for k, v in m.items() if pd.notna(v)}


sample = judge_sample(eval_set, EVAL_JUDGE_SAMPLE)


def run_config(name: str, top_k: int, query_type: str):
    rag = RAGMarillion(index, LLM_ENDPOINT, top_k=top_k, query_type=query_type)
    rows = []
    with mlflow.start_run(run_name=name):
        mlflow.set_tags({**MODE_TAGS, "split": EVAL_SPLIT, "tipo": "rag"})
        mlflow.log_params({
            "top_k": top_k, "query_type": query_type, "embedding": EMBEDDING_ENDPOINT,
            "llm": LLM_ENDPOINT, "chunk_size": CHUNK_SIZE_WORDS, "overlap": CHUNK_OVERLAP_WORDS,
            "prepend_chapter": PREPEND_CHAPTER, "n_questions": len(eval_set), "n_judged": len(sample),
        })

        # 1) Recuperação e recusa: todas as perguntas, sem juiz
        for e in eval_set:
            docs = rag.retrieve(e["question"])
            row = {"id": e["id"], "category": e["category"]}
            if e["category"] == "unanswerable":
                row["refused"] = REFUSAL_TEXT.lower() in rag.generate(e["question"], docs).lower()
            else:
                hits = [{"text": d.page_content} for d in docs]
                row["hit"] = hit_at_k(hits, e["expected_terms"])
                row["rr_terms"] = reciprocal_rank(hits, e["expected_terms"])
                if e.get("evidence_pages"):
                    pages = [(int(d.metadata["page_start"]), int(d.metadata["page_end"])) for d in docs]
                    row.update(page_scores(pages, list(e["evidence_pages"]), top_k))
            rows.append(row)
        df = pd.DataFrame(rows)
        metrics = retrieval_summary(df)
        mlflow.log_metrics(metrics)

        # 2) Resposta: juízes LLM na amostra
        jm = {}
        if sample:
            result = mlflow.genai.evaluate(data=as_eval_data(sample),
                                           predict_fn=lambda question: rag.answer(question), scorers=judges())
            jm = judged(result)
    return df, metrics, jm


def run_closed_book():
    llm = ClosedBookLLM(LLM_ENDPOINT)
    with mlflow.start_run(run_name="llm_sem_contexto"):
        mlflow.set_tags({**MODE_TAGS, "split": EVAL_SPLIT, "tipo": "linha_de_base"})
        mlflow.log_params({"llm": LLM_ENDPOINT, "n_judged": len(sample)})
        result = mlflow.genai.evaluate(data=as_eval_data(sample),
                                       predict_fn=lambda question: llm.answer(question), scorers=closed_book_judges())
    return judged(result)

# COMMAND ----------

# Ablação mínima + linha de base sem contexto
configs = [
    ("ann_k3", 3, "ann"),
    ("ann_k5", 5, "ann"),
    ("hybrid_k5", 5, "hybrid"),
]
results = {name: run_config(name, k, qt) for name, k, qt in configs}
closed_book = run_closed_book() if sample else {}

# COMMAND ----------

# MAGIC %md
# MAGIC ### Resumo
# MAGIC Uma linha por configuração. A linha `llm_sem_contexto` só tem as colunas dos juízes: sem busca
# MAGIC não há recuperação para medir.

# COMMAND ----------

summary = pd.DataFrame({name: {**m, **jm} for name, (_, m, jm) in results.items()}).T
if closed_book:
    summary = pd.concat([summary, pd.DataFrame([closed_book], index=["llm_sem_contexto"])])
display(summary.round(3))

# COMMAND ----------

# Acerto da busca por categoria: Recall@k por página quando há evidence_pages, senão hit@k por termos
by_category = {}
for name, (df, _, _) in results.items():
    answerable = df[df.category != "unanswerable"].copy()
    answerable["acerto_busca"] = answerable["recall"].fillna(answerable["hit"]) if "recall" in answerable else answerable["hit"]
    by_category[name] = answerable.groupby("category")["acerto_busca"].mean()
display(pd.DataFrame(by_category).round(3))

# COMMAND ----------

# Onde a busca errou? Perguntas sem acerto em cada configuração (até 20)
for name, (df, _, _) in results.items():
    answerable = df[df.category != "unanswerable"]
    ok = answerable["recall"].fillna(answerable["hit"]) if "recall" in answerable else answerable["hit"]
    misses = answerable.loc[~ok.astype(bool), "id"].tolist()
    print(f"{name} → {len(misses)} sem acerto: {misses[:20]}")
