# RAGMarillion · RAG sobre O Silmarillion no Databricks Free Edition

Sistema de *Retrieval-Augmented Generation* sobre **O Silmarillion**, construído de ponta a ponta no
Databricks Free Edition: ingestão de PDF → chunking por capítulo → Vector Search (híbrido) →
LLM com citações → avaliação com MLflow, incluindo **testes contrafactuais** para medir se o
modelo usa o contexto ou a memória.

> **Sobre o texto do livro:** O Silmarillion é protegido por direitos autorais. Este repositório
> contém **apenas código**. O PDF, os chunks e as saídas dos notebooks não são versionados.
> Para reproduzir, use a sua própria cópia do livro.

---

## Por que o Silmarillion é um bom benchmark de RAG

| Desafio | Exemplo | O que testa |
|---|---|---|
| Uma entidade, muitos nomes | Túrin = Neithan, Mormegil, Turambar | Resolução de aliases |
| Nomes quase iguais | Finwë, Fingolfin, Finarfin, Fingon, Finrod | Busca híbrida vs. só vetorial |
| Fatos espalhados | Lúthien → Dior → Elwing → Elrond | Perguntas multi-hop |
| O LLM já conhece a obra | Qualquer pergunta | Recuperação precisa ser medida **separada** da resposta |

## Arquitetura

```
PDF (Volume UC) ──► pages (Delta) ──► chunks (Delta, CDF) ──► Vector Search index (Delta Sync)
                                                                     │  embeddings gerenciados
                                         pergunta ──► retrieve (top-k, hybrid) ──► LLM ──► resposta + [citações]
                                                                     │
                                                    MLflow Tracing + mlflow.genai.evaluate
```

## Estrutura

```
notebooks/
  00_config.py          # todos os parâmetros (catálogo, modelos, chunking, top-k)
  01_setup.py           # schema, volume, endpoint de Vector Search
  02_ingest_pdf.py      # PDF → tabela pages (+ inspeção de ruído e títulos)
  03_chunking.py        # pages → chunks (Change Data Feed ligado)
  04_vector_index.py    # índice Delta Sync + teste ann vs hybrid
  05_rag_chain.py       # cadeia RAG com tracing
  06_evaluation.py      # hit@k, MRR, recusa, juízes LLM, ablação
  07_counterfactual.py  # adultera um fato e verifica se o modelo segue o contexto
src/
  chunking.py           # funções puras, testáveis fora do Databricks
  retrieval.py          # prompt, parsing, métricas de recuperação
  rag.py                # classe RAGMarillion (MLflow traced)
data/
  eval_questions.jsonl  # gabarito: factual, aliases, nomes parecidos, multi-hop, sem resposta
tests/                  # pytest para o chunking e as métricas
```

---

## Passo a passo

### 1. Criar a conta no Databricks Free Edition
1. Acesse <https://login.databricks.com/?intent=CE_SIGN_UP> e crie a conta (o antigo Community Edition foi aposentado).
2. Opcional: verifique a identidade com o LinkedIn para aumentar alguns limites.

**Limites que afetam este projeto:** só computação serverless; **1 endpoint de Vector Search**
(1 unidade); sem Direct Vector Access (por isso usamos índice Delta Sync); sem serving em GPU.

### 2. Publicar o repositório no GitHub
No seu computador:
```bash
cd RAGMarillion
git init && git add . && git commit -m "RAGMarillion: estrutura inicial"
gh repo create RAGMarillion --public --source=. --push
# ou crie o repo vazio no github.com e: git remote add origin <url> && git push -u origin main
```
Confira que **nenhum PDF** entrou: `git ls-files | grep -i pdf` deve voltar vazio.

### 3. Conectar o repositório ao Databricks
1. No workspace: **Workspace > Home > Create > Git folder**.
2. Cole a URL do repo. Para dar *push* de dentro do Databricks, configure um token do GitHub em
   **Settings > Linked accounts**.
3. Os notebooks aparecem em `RAGMarillion/notebooks/`. Eles importam `src/` automaticamente
   (`sys.path.append("..")`).

> Se Git folder não estiver disponível, importe os arquivos manualmente
> (**Workspace > Import**) mantendo a mesma estrutura de pastas.

### 4. Ajustar a configuração (`00_config`)
- `EMBEDDING_ENDPOINT`: `databricks-qwen3-embedding-0-6b` é multilíngue (bom para PDF em português);
  para PDF em inglês, `databricks-gte-large-en` também serve.
- `LLM_ENDPOINT`: qualquer endpoint de chat listado em **Serving**.
- O notebook `01` confere se os dois existem no seu workspace.

### 5. Rodar o setup (`01_setup`)
Cria `workspace.ragmarillion`, o Volume `raw` e o endpoint `ragmarillion-vs`.
A primeira subida do endpoint leva alguns minutos.

### 6. Subir o PDF
**Catalog > workspace > ragmarillion > raw > Upload to this volume**. O nome do arquivo
precisa bater com `PDF_FILENAME` no `00_config`.

### 7. Ingerir e inspecionar (`02_ingest_pdf`)
Extrai o texto com `pypdf`. Antes de seguir, use as células de inspeção para:
- adicionar em `DROP_LINE_PATTERNS` o cabeçalho corrente e outros ruídos;
- descobrir como os títulos de capítulo aparecem e preencher `CHAPTER_REGEX` no `00_config`.

Se muitas páginas vierem sem texto, o PDF é escaneado e precisa de OCR antes.

### 8. Chunking (`03_chunking`)
Chunks de ~350 palavras com 60 de overlap, sem atravessar capítulos, com o título do capítulo
injetado no texto (`PREPEND_CHAPTER`). Confira a tabela de chunks por capítulo: se tudo cair em
"Início", o `CHAPTER_REGEX` não está pegando.

### 9. Índice vetorial (`04_vector_index`)
Cria o índice Delta Sync com embeddings gerenciados e compara `ann` vs `hybrid` numa pergunta.
- Mudou os chunks? Rode `index.sync()`.
- Mudou o modelo de embedding? Apague e recrie o índice.

### 10. Cadeia RAG (`05_rag_chain`)
Pergunte à vontade. Abra o experimento no MLflow, aba **Traces**, para ver exatamente quais
chunks foram recuperados em cada resposta.

### 11. Avaliação (`06_evaluation`)
Roda uma ablação (`ann_k3`, `ann_k5`, `hybrid_k5`) e registra no MLflow:
- **hit@k / MRR**: proxy de recall pelos termos esperados de cada pergunta;
- **taxa de recusa** nas perguntas sem resposta no livro;
- **Correctness** e **RetrievalGroundedness** (juízes LLM).

Se os juízes padrão não estiverem disponíveis no Free Edition, defina `JUDGE_MODEL` no `00_config`
com um endpoint do workspace.

### 12. Teste contrafactual (`07_counterfactual`)
Troca um fato nos chunks (quem forjou as Silmarils), re-sincroniza o índice, pergunta de novo e
restaura os originais. Mede se o modelo **segue o contexto** ou **corrige com a memória**.

### 13. Commitar só código
Pelo Git folder do Databricks (ou localmente), commite as mudanças nos `.py`. Notebooks no formato
`.py` não guardam saídas, então o texto do livro não vaza para o GitHub.

---

## Testes locais
```bash
pip install pytest
pytest
```

## Ideias para evoluir
- **Aumentar o gabarito** para 40–60 perguntas, balanceando as categorias.
- **Expansão de query por aliases**: usar o índice de nomes do livro para mapear apelidos ao nome canônico.
- **Reranker** (cross-encoder) sobre um top-20.
- **Grafo de entidades** a partir das genealogias para perguntas multi-hop.
- **Comparar LLMs** grandes e pequenos no teste contrafactual.
- **Servir como app** (1 Databricks App permitido no Free Edition).

## Licença
Código sob MIT. O Silmarillion © The Tolkien Estate; nenhum trecho da obra está incluído.
