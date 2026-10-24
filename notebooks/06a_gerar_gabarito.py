# Databricks notebook source
# MAGIC %md
# MAGIC # 06a · Gabarito sintético
# MAGIC Gera perguntas de avaliação a partir do próprio livro, para medir a recuperação em escala.
# MAGIC
# MAGIC 1. Sorteia `SYNTH_N_CHUNKS` chunks da história (sem glossário, mapas etc.).
# MAGIC 2. Para cada um, um LLM lê **só aquele trecho** e escreve uma pergunta e a resposta.
# MAGIC 3. Filtros descartam o que não presta (resposta fora do trecho, pergunta ambígua, cópia do texto).
# MAGIC 4. As perguntas aprovadas vão para a tabela `SYNTH_TABLE`, com o chunk e as páginas de origem
# MAGIC    e a divisão fixa em desenvolvimento (`dev`) e teste (`test`).
# MAGIC 5. Você revisa uma amostra de 30 e marca as ruins na última célula.
# MAGIC
# MAGIC O chunk e a página de origem vêm do sorteio, não do LLM: é isso que permite medir se a busca
# MAGIC trouxe o trecho certo. Rodar de novo **não** regera o gabarito (a revisão seria perdida),
# MAGIC a não ser com `SYNTH_OVERWRITE = True`.
# MAGIC
# MAGIC ⚠️ As perguntas derivam do texto do livro: ficam numa tabela no Databricks, nunca no GitHub.

# COMMAND ----------

# MAGIC %pip install -q "mlflow[databricks]>=3.1"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import os, sys, time
sys.path.append(os.path.abspath(".."))
from collections import Counter
from databricks.sdk import WorkspaceClient
from mlflow.deployments import get_deploy_client
from src import checks
from src.synth import build_messages, check_generation, is_excluded, parse_generation, split_for

available = {e.name for e in WorkspaceClient().serving_endpoints.list()}
rep = checks.Report("06a · Modelo")
rep.add("Modelo gerador existe", checks.Result(
    SYNTH_LLM_ENDPOINT in available,
    SYNTH_LLM_ENDPOINT if SYNTH_LLM_ENDPOINT in available else f"'{SYNTH_LLM_ENDPOINT}' não existe; troque SYNTH_LLM_ENDPOINT"))
if SYNTH_LLM_ENDPOINT == LLM_ENDPOINT:
    rep.info("Modelo gerador", "é o mesmo que responde no RAG; se houver outro em Serving, prefira-o")
rep.finish()

# COMMAND ----------

def generate(messages: list[dict], tries: int = 3) -> str:
    """Chama o LLM com algumas novas tentativas (o Free Edition limita a taxa de chamadas)."""
    client = get_deploy_client("databricks")
    for attempt in range(tries):
        try:
            resp = client.predict(endpoint=SYNTH_LLM_ENDPOINT,
                                  inputs={"messages": messages, "temperature": 0.3, "max_tokens": 300})
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == tries - 1:
                print(f"Falhou: {type(e).__name__}: {e}")
                return ""
            time.sleep(10 * (attempt + 1))


if spark.catalog.tableExists(SYNTH_TABLE) and not SYNTH_OVERWRITE:
    print(f"{SYNTH_TABLE} já existe: usando o gabarito gravado (SYNTH_OVERWRITE = False).")
else:
    chunks = [r.asDict() for r in spark.table(CHUNKS_TABLE).collect()]
    eligible = sorted((c for c in chunks if not is_excluded(c["chapter"], SYNTH_EXCLUDE_CHAPTERS)),
                      key=lambda c: c["chunk_id"])
    import random
    sample = random.Random(SYNTH_SEED).sample(eligible, min(SYNTH_N_CHUNKS, len(eligible)))
    print(f"{len(eligible)} chunks elegíveis; {len(sample)} sorteados")

    rows, reasons = [], Counter()
    for i, c in enumerate(sample, start=1):
        gen = parse_generation(generate(build_messages(c["text"])))
        reason = check_generation(gen, c["text"], SYNTH_MAX_COPY_WORDS)
        if reason:
            reasons[reason] += 1
        else:
            qid = f"s{len(rows) + 1:03d}"
            rows.append({
                "id": qid, "category": "sintetica", "split": split_for(qid),
                "question": gen["pergunta"].strip(), "expected_response": gen["resposta"].strip(),
                "expected_terms": [t.strip() for t in gen["termos"]],
                "source_chunk": c["chunk_id"], "chapter": c["chapter"],
                "evidence_pages": list(range(c["page_start"], c["page_end"] + 1)),
                "generator": SYNTH_LLM_ENDPOINT, "status": "ok",
            })
        if i % 20 == 0:
            print(f"{i}/{len(sample)}: {len(rows)} aprovadas")

    rep = checks.Report("06a · Geração")
    rep.add("Perguntas aprovadas", checks.Result(
        len(rows) >= SYNTH_MIN_KEPT, f"{len(rows)} de {len(sample)}; mínimo {SYNTH_MIN_KEPT}"), level=BOOK_LEVEL)
    rep.info("Descartes por motivo", dict(reasons) or "nenhum")
    rep.info("Divisão", dict(Counter(r["split"] for r in rows)))
    rep.finish()
    if not rows:
        raise RuntimeError("Nenhuma pergunta aprovada: veja os motivos de descarte acima.")

    (spark.createDataFrame(rows).write.mode("overwrite").option("overwriteSchema", "true")
        .saveAsTable(SYNTH_TABLE))
    print(f"Gravado em {SYNTH_TABLE}: {len(rows)} perguntas")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Revisão humana por amostra
# MAGIC Leia as 30 perguntas abaixo, cada uma com o trecho de onde saiu. Uma pergunta é **ruim** se:
# MAGIC a resposta está errada para aquele trecho; a pergunta é ambígua ou tem várias respostas no livro;
# MAGIC ou não faz sentido. Anote os ids ruins em `REVIEW_REJECT` na célula seguinte e rode só ela.

# COMMAND ----------

from pyspark.sql import functions as F

review = (spark.table(SYNTH_TABLE).orderBy(F.xxhash64("id")).limit(30)
          .join(spark.table(CHUNKS_TABLE).select(F.col("chunk_id").alias("source_chunk"), "text"), "source_chunk")
          .orderBy("id").collect())
for r in review:
    print(f"[{r.id}] ({r.status}) {r.question}\n   → {r.expected_response}\n"
          f"   trecho {r.source_chunk}, p. {r.evidence_pages[0]}: {r.text[:300]}…\n")

# COMMAND ----------

REVIEW_REJECT = []  # ex.: ["s017", "s042"]

reviewed = [r.id for r in review]
unknown = [i for i in REVIEW_REJECT if i not in reviewed]
if unknown:
    raise ValueError(f"Ids fora da amostra revisada: {unknown}")
if REVIEW_REJECT:
    ids_sql = ", ".join(f"'{i}'" for i in REVIEW_REJECT)
    spark.sql(f"UPDATE {SYNTH_TABLE} SET status = 'rejeitada' WHERE id IN ({ids_sql})")
error_rate = len(REVIEW_REJECT) / len(reviewed) if reviewed else 0.0
print(f"Taxa de erro estimada do gabarito: {error_rate:.0%} ({len(REVIEW_REJECT)} de {len(reviewed)} revisadas)")
print("Diferenças entre configurações da ordem dessa taxa são ruído do gabarito, não melhora real.")
