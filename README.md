# RAGMarillion · RAG sobre O Silmarillion no Databricks Free Edition

Sistema de *Retrieval-Augmented Generation* sobre **O Silmarillion**, construído de ponta a ponta no
Databricks Free Edition: ingestão de PDF → chunking por capítulo → Vector Search (híbrido) →
LLM com citações → avaliação com MLflow, incluindo **testes contrafactuais** para medir se o
modelo usa o contexto ou a memória.

> **Sobre o texto do livro:** O Silmarillion é protegido por direitos autorais. Este repositório
> contém **apenas código**. O PDF, os chunks e as saídas dos notebooks não são versionados.
> Para reproduzir, use a sua própria cópia do livro.

**Andamento:** o que já foi feito e os próximos passos estão em [docs/progresso.md](docs/progresso.md); as métricas e os resultados da avaliação, em [docs/metricas.md](docs/metricas.md); e o raciocínio por trás da avaliação, em [docs/discussao-avaliacao.md](docs/discussao-avaliacao.md).

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
  06a_gerar_gabarito.py # perguntas sintéticas geradas dos próprios trechos, com revisão por amostra
  06_evaluation.py      # Recall@k/nDCG por página, recusa, juízes LLM, ablação, LLM sem contexto
  07_counterfactual.py  # adultera um fato e verifica se o modelo segue o contexto
src/
  chunking.py           # funções puras, testáveis fora do Databricks
  retrieval.py          # prompt, parsing, métricas de recuperação
  rag.py                # classe RAGMarillion (MLflow traced) e a linha de base sem contexto
  checks.py             # verificações de qualidade de cada etapa
  synth.py              # prompt e filtros do gabarito sintético
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
- `PAGE_RANGE`: deixe `None` para o livro inteiro. Veja [Modo de teste](#modo-de-teste).

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

O extrator do texto é escolhido em `PDF_EXTRACTOR` (`pypdf`, `pypdf_layout` ou `pymupdf`). A célula
"Comparar extratores" conta as palavras grudadas ("paraMinas") que cada um deixa numa amostra de
páginas; use o que deixar menos.

### 8. Chunking (`03_chunking`)
Chunks de ~350 palavras com 60 de overlap, sem atravessar capítulos, com o título do capítulo
injetado no texto (`PREPEND_CHAPTER`). Os títulos são detectados linha a linha; um título igual ao
do capítulo atual (cabeçalho corrente) é ignorado. Confira a tabela de títulos detectados e a de
chunks por capítulo: se tudo cair em "Início", o `CHAPTER_REGEX` não está pegando.

### 9. Índice vetorial (`04_vector_index`)
Cria o índice Delta Sync com embeddings gerenciados e compara `ann` vs `hybrid` numa pergunta.
- Mudou os chunks? Rode `index.sync()`.
- Mudou o modelo de embedding? Apague e recrie o índice.

### 10. Cadeia RAG (`05_rag_chain`)
Pergunte à vontade. Abra o experimento no MLflow, aba **Traces**, para ver exatamente quais
chunks foram recuperados em cada resposta.

### 11. Gabarito sintético (`06a_gerar_gabarito`)
Um LLM lê **um** chunk sorteado de cada vez e escreve uma pergunta que aquele trecho responde. Filtros
descartam respostas fora do trecho, perguntas ambíguas e cópias do texto; o chunk e as páginas de origem
vêm do sorteio, e são eles que permitem medir a recuperação. As perguntas ficam na tabela `SYNTH_TABLE`
(no Databricks, não no GitHub), divididas em `dev` e `test`. No fim, revise a amostra de 30 e marque as
ruins em `REVIEW_REJECT`: a fração rejeitada estima o ruído do gabarito.

### 12. Avaliação (`06_evaluation`)
Roda uma ablação (`ann_k3`, `ann_k5`, `hybrid_k5`) e uma linha de base `llm_sem_contexto` (o mesmo LLM
respondendo de memória) e registra no MLflow:
- **Recall@k, MRR, nDCG@k e Precisão@k por página**, nas perguntas com `evidence_pages` (as sintéticas):
  o trecho buscado cobre a página da resposta? Independe do chunking;
- **hit@k / MRR por termos** no gabarito manual;
- **taxa de recusa** nas perguntas sem resposta no livro;
- **Correctness**, **RetrievalGroundedness** e **RetrievalSufficiency** (juízes LLM) numa amostra de
  `EVAL_JUDGE_SAMPLE` perguntas.

Compare configurações com `EVAL_SPLIT = "dev"` e use `"test"` uma vez só, para confirmar a escolhida.
Cada configuração em `CONFIGS` também escolhe a versão do prompt da resposta (`PROMPTS`) e a estratégia
de busca (`STRATEGIES`, ambos em `src/retrieval.py`), para medir essas mudanças do mesmo jeito:

| Estratégia | O que faz |
|---|---|
| `simples` | Os k trechos mais parecidos com a pergunta |
| `vizinhos` | Os k, mais o trecho anterior e o seguinte dos 2 primeiros, do mesmo capítulo |
| `diversa` | Dos 20 melhores, k com no máximo 2 por capítulo |
| `por_nome` | Uma busca por nome próprio da pergunta, intercalada com a busca da pergunta inteira |

Como algumas estratégias mandam mais texto ao LLM, a métrica `context_words` mostra quanto: compare
acertos e tamanho do contexto juntos.
Se os juízes padrão não estiverem disponíveis no Free Edition, defina `JUDGE_MODEL` no `00_config`
com um endpoint do workspace. O raciocínio por trás dessa avaliação está em
[docs/discussao-avaliacao.md](docs/discussao-avaliacao.md).

### 13. Teste contrafactual (`07_counterfactual`)
Troca um fato nos chunks (quem forjou as Silmarils), espera o índice mostrar o texto trocado,
pergunta de novo e restaura os originais, mesmo se algo falhar no meio. Mede se o modelo **segue o
contexto** (cita o fato falso e não o verdadeiro) ou **corrige com a memória**.

### 14. Commitar só código
Pelo Git folder do Databricks (ou localmente), commite as mudanças nos `.py`. Notebooks no formato
`.py` não guardam saídas, então o texto do livro não vaza para o GitHub.

---

## Verificações automáticas

Cada notebook termina com um resumo de verificações. **ERRO** para a execução antes de gravar
dados ruins; **AVISO** só pede que você confira. Os limites ficam no `00_config`.

| Notebook | O que verifica |
|---|---|
| 01 Setup | Modelos de embedding e LLM existem no workspace |
| 02 Ingestão | PDF no Volume; páginas sem texto (OCR?); total de palavras; termos-âncora (livro certo, acentos íntegros); caracteres corrompidos; cabeçalho/rodapé repetido, com sugestão de padrão para `DROP_LINE_PATTERNS` |
| 03 Chunking | `CHAPTER_REGEX` definido; número de capítulos; títulos que reaparecem (cabeçalho alternado); linhas que batem no regex mas são longas demais; capítulos pequenos ou dominantes; chunks curtos; nenhuma palavra perdida |
| 04 Índice | Linhas no índice = linhas na tabela; auto-recuperação (buscar um trecho de um chunk devolve esse chunk) |
| 05 RAG | Citações da resposta estão entre os chunks recuperados |
| 06a Gabarito sintético | Modelo gerador existe; mínimo de perguntas aprovadas; descartes por motivo; taxa de erro da revisão |
| 06 Avaliação | Gabarito bem formado; gabarito sintético presente; termos esperados existem no texto da sua edição; juiz LLM responde |
| 07 Contrafactual | Fato falso ausente do contexto original; índice reflete a troca antes da pergunta; restauração confirmada |

## Modo de teste

Para ajustar `DROP_LINE_PATTERNS` e `CHAPTER_REGEX` sem processar o livro inteiro, defina no `00_config`:

```python
PAGE_RANGE = (40, 70)  # páginas do PDF, inclusive
```

Escolha um trecho que atravesse a passagem entre dois capítulos. No modo de teste:
- tabelas e índice ganham o sufixo `_teste` e não sobrescrevem os do livro inteiro;
- checagens que só fazem sentido no livro inteiro (total de palavras, número de capítulos,
  termos-âncora) viram informação ou AVISO;
- a avaliação usa só as perguntas cujos termos aparecem no trecho;
- runs do MLflow levam a tag `modo=teste` e o intervalo de páginas.

Volte para `PAGE_RANGE = None` e rode do `02` em diante para o livro inteiro.

## Aplicação no terminal

Depois de rodar os notebooks até o 04, dá para perguntar direto do seu computador. A aplicação usa o
índice e o LLM do Databricks, com a configuração escolhida na avaliação (busca híbrida, 5 trechos), e
mostra a resposta com as fontes citadas, capítulo e página.

```bash
pip install -r requirements-app.txt
python app/perguntar.py "Quem forjou as Silmarils?"
python app/perguntar.py            # modo interativo: Enter vazio ou 'sair' encerra
python app/perguntar.py --trechos  # mostra também o começo dos trechos recuperados
python app/perguntar.py --completo # mostra os trechos recuperados inteiros
python app/perguntar.py --prompt v1 "..."  # usa outra versão do prompt da resposta
python app/perguntar.py --estrategia diversa "..."  # usa outra estratégia de busca
```

**Credenciais.** Crie um token em **Settings > Developer > Access tokens** no Databricks e configure
**fora do repositório**, por variáveis de ambiente (`DATABRICKS_HOST` e `DATABRICKS_TOKEN`) ou pelo
arquivo `~/.databrickscfg`. Sem elas, a aplicação explica o que configurar. Com `--mlflow`, cada
pergunta é registrada nos traces do experimento `ragmarillion`.

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
