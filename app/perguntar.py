"""RAGMarillion no terminal: pergunte sobre O Silmarillion e receba a resposta com as fontes.

    python app/perguntar.py "Quem forjou as Silmarils?"
    python app/perguntar.py                 # modo interativo
    python app/perguntar.py --trechos       # mostra também o começo dos trechos recuperados
    python app/perguntar.py --completo      # mostra os trechos recuperados inteiros

Usa o índice e o LLM que já estão no Databricks. Credenciais: DATABRICKS_HOST e
DATABRICKS_TOKEN no ambiente, ou um perfil em ~/.databrickscfg (fora do repositório).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.answer_format import excerpt, format_sources, page_label  # noqa: E402
from src.retrieval import DEFAULT_PROMPT, PROMPTS, STRATEGIES  # noqa: E402

# Os mesmos nomes do 00_config, com a configuração escolhida na avaliação (hybrid, 5 trechos)
DEFAULTS = {
    "endpoint": "ragmarillion-vs",
    "indice": "workspace.ragmarillion.chunks_index",
    "llm": "databricks-meta-llama-3-3-70b-instruct",
    "top_k": 5,
    "busca": "hybrid",
}

HELP_CREDENCIAIS = """
Para conectar, o Databricks precisa saber quem você é. Escolha um jeito (nunca no repositório):
  1. Variáveis de ambiente, no PowerShell:
       $env:DATABRICKS_HOST  = "https://<seu-workspace>.cloud.databricks.com"
       $env:DATABRICKS_TOKEN = "<token pessoal>"
  2. Um arquivo ~/.databrickscfg com:
       [DEFAULT]
       host  = https://<seu-workspace>.cloud.databricks.com
       token = <token pessoal>
O token pessoal se cria no Databricks em Settings > Developer > Access tokens."""


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pergunte sobre O Silmarillion.")
    p.add_argument("pergunta", nargs="*", help="a pergunta; sem ela, abre o modo interativo")
    p.add_argument("--trechos", action="store_true", help="mostra o começo dos trechos recuperados")
    p.add_argument("--completo", action="store_true", help="mostra os trechos recuperados inteiros")
    p.add_argument("--top-k", type=int, default=DEFAULTS["top_k"], help="trechos enviados ao LLM")
    p.add_argument("--busca", choices=["hybrid", "ann"], default=DEFAULTS["busca"], help="tipo de busca")
    p.add_argument("--endpoint", default=DEFAULTS["endpoint"], help="endpoint de busca")
    p.add_argument("--indice", default=DEFAULTS["indice"], help="índice de busca")
    p.add_argument("--llm", default=DEFAULTS["llm"], help="endpoint do LLM")
    p.add_argument("--prompt", choices=sorted(PROMPTS), default=DEFAULT_PROMPT, help="versão do prompt da resposta")
    p.add_argument("--estrategia", choices=STRATEGIES, default="simples", help="estratégia de busca")
    p.add_argument("--mlflow", action="store_true", help="registra cada pergunta no experimento do MLflow")
    return p.parse_args(argv)


def connect(args: argparse.Namespace):
    import mlflow
    from databricks.ai_search.client import AISearchClient
    from src.rag import RAGMarillion

    if args.mlflow:
        from databricks.sdk import WorkspaceClient
        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment(f"/Users/{WorkspaceClient().current_user.me().user_name}/ragmarillion")
    else:
        mlflow.tracing.disable()  # sem isso o MLflow gravaria traces numa pasta local

    host, token = os.environ.get("DATABRICKS_HOST"), os.environ.get("DATABRICKS_TOKEN")
    creds = {"workspace_url": host.rstrip("/"), "personal_access_token": token} if host and token else {}
    index = AISearchClient(disable_notice=True, **creds).get_index(args.endpoint, args.indice)
    return RAGMarillion(index, args.llm, top_k=args.top_k, query_type=args.busca, prompt_version=args.prompt,
                        strategy=args.estrategia)


def answer(rag, question: str, show_passages: bool, full: bool = False) -> None:
    text = rag.answer(question)
    print(f"\n{text}")
    sources = format_sources(text, rag.last_docs)
    if sources:
        print("\nFontes:")
        for line in sources:
            print(f"  {line}")
    if show_passages or full:
        print("\nTrechos recuperados:")
        for d in rag.last_docs:
            print(f"  [{d.id}] {d.metadata['chapter']}, {page_label(d.metadata)}\n    {excerpt(d.page_content, None if full else 300)}")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # acentos no terminal do Windows
        except (AttributeError, ValueError):
            pass
    # O MLflow imprime dicas e avisos de autenticação que não interessam a quem só pergunta
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    os.environ.setdefault("MLFLOW_LOGGING_LEVEL", "ERROR")  # lido pelo MLflow ao ser importado
    logging.getLogger("mlflow").setLevel(logging.ERROR)
    args = parse_args(argv)
    try:
        rag = connect(args)
    except Exception as e:
        first_line = str(e).strip().splitlines()[0][:300] if str(e).strip() else ""
        print(f"Não consegui conectar ao Databricks: {type(e).__name__}: {first_line}\n{HELP_CREDENCIAIS}",
              file=sys.stderr)
        return 1

    if args.pergunta:
        answer(rag, " ".join(args.pergunta), args.trechos, args.completo)
        return 0

    print("RAGMarillion · pergunte sobre O Silmarillion. Enter vazio ou 'sair' para encerrar.")
    while True:
        try:
            question = input("\nPergunta> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in {"sair", "exit", "quit"}:
            break
        try:
            answer(rag, question, args.trechos, args.completo)
        except Exception as e:
            print(f"Erro: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
