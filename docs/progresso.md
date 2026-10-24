# RAGMarillion — o que foi feito até agora

Atualizado em 24/10/2026 · velosomn

## Visão geral

O RAGMarillion responde perguntas sobre O Silmarillion citando os trechos do livro, e hoje roda de ponta a ponta no livro inteiro: 1.020 páginas, 529 chunks, 36 capítulos. A ingestão, o chunking, o índice e a cadeia RAG estão validados. A avaliação sistemática (notebook 06) e o teste contrafactual (07) ainda não rodaram.

O repositório é público em [github.com/velosomn/RAGMarillion](https://github.com/velosomn/RAGMarillion) e contém só código. O PDF, os chunks e as saídas dos notebooks ficam no Databricks, por causa dos direitos autorais da obra.

| Peça | Escolha |
| --- | --- |
| Plataforma | Databricks Free Edition, computação Serverless (ambiente v6) |
| Armazenamento | Unity Catalog: schema `workspace.ragmarillion`, Volume `raw`, tabelas Delta `pages` e `chunks` |
| Busca | Databricks AI Search (antigo Vector Search), índice Delta Sync, busca híbrida |
| Embeddings | `databricks-qwen3-embedding-0-6b` (multilíngue, bom para o PDF em português) |
| LLM | `databricks-meta-llama-3-3-70b-instruct`, temperatura 0 |
| Rastreio e avaliação | MLflow 3 (Tracing e `mlflow.genai.evaluate`) |
| Testes locais | pytest, 31 testes sobre chunking e verificações |

## Linha do tempo

Em dois dias, o projeto saiu de um zip com a estrutura inicial para um RAG validado no livro inteiro, em 15 commits. A tabela lista os marcos, do mais recente ao mais antigo.

| Data | Commit | O que mudou |
| --- | --- | --- |
| 24/10 | `444f1d4` | Junção de título guiada pelo regex: corrige "DA QUINTA" e "DE TÚRIN" cortados |
| 24/10 | `7f45db1` | O 02 passa a mostrar os títulos que o chunking vai usar e verifica os capítulos |
| 24/10 | `b4c09f4` | Regex final com as 36 seções e `PAGE_RANGE = None` (feito no Databricks) |
| 24/10 | `ecad647` | O chunking ignora o sumário (páginas com 3 ou mais títulos) |
| 24/10 | `c6b4fbb` | Título de capítulo em duas linhas é juntado; aviso de autenticação silenciado |
| 24/10 | `869cac7` | Primeiro push feito pelo Databricks: nome do PDF, modo de teste, regex inicial |
| 23/10 | `616cef2` | Conversão de ligaduras tipográficas (ﬁ, ﬂ) na limpeza do texto |
| 23/10 | `9850d3f` | Troca de `databricks-vectorsearch` por `databricks-ai-search` |
| 23/10 | `af38039` | Verificações por etapa (`src/checks.py`) e modo de teste por páginas |
| 23/10 | `e9890c9` | Renomeação de todo o projeto para RAGMarillion |
| 23/10 | `d083f77` | Estrutura inicial, a partir do zip `silmarillion-rag` |

O repositório começou como `RAGMarilion` (um L) e foi renomeado para `RAGMarillion` no GitHub e na pasta local. O link antigo redireciona para o novo.

## Arquitetura

O fluxo é uma sequência de notebooks em que cada um grava uma tabela ou um índice que o próximo lê. A lógica fica em `src/`, como funções puras testáveis fora do Databricks, e os notebooks só as chamam.

![Arquitetura: do PDF à resposta citada, cada notebook grava o que o próximo lê](img/arquitetura.png)

O `00_config` reúne todos os parâmetros e é carregado no início de cada notebook; o `01` prepara o ambiente uma vez.

| Módulo | Papel |
| --- | --- |
| `src/chunking.py` | Limpeza do texto, detecção de títulos e sumário, divisão em chunks |
| `src/checks.py` | Todas as verificações ERRO/AVISO e o resumo de cada notebook |
| `src/retrieval.py` | Prompt, leitura dos resultados da busca, métricas hit@k e MRR, esperas pelo índice |
| `src/rag.py` | Classe `RAGMarillion`: busca, geração e rastreio no MLflow |

## Ambiente Databricks

O ambiente está montado e funcionando, mas quatro problemas apareceram no caminho. Todos foram resolvidos e estão registrados no código ou no repositório.

**Montagem**

1. Conta no Databricks Free Edition.
2. Git folder em Workspace > Home > Create > Git folder, apontando para o repositório público.
3. Notebook 01: cria o schema, o Volume `raw` e o endpoint de busca `ragmarillion-vs` (ficou ONLINE), e confirma que os dois modelos existem no workspace.
4. Upload do PDF no Volume.

**Problemas e soluções**

| Problema | Causa | Solução |
| --- | --- | --- |
| O Python não reiniciava no `%pip install` | `databricks-vectorsearch` 0.75 exige `protobuf<6`, e o ambiente Serverless v6 vem com o 6.33.5 | Troca pelo sucessor oficial `databricks-ai-search`, mesma API, sem restrição de protobuf |
| Conflito de merge no `01_setup` | O Genie alterou a célula de instalação ao mesmo tempo que o GitHub | Mantida a versão do GitHub ("upstream") |
| Push do Databricks recusado | A credencial Git não tinha um token com escrita | Token *fine-grained* só para o repositório, com Contents: Read and write, cadastrado como credencial nova |
| `PDF não encontrado` | O arquivo no Volume se chama `O Silmarillion - J.R.R. Tolkien.pdf` | `PDF_FILENAME` ajustado no `00_config`; a mensagem de erro já listava os arquivos do Volume |

O Databricks acrescenta um cabeçalho `environment_version = "6"` aos notebooks que executa. Ele registra a versão do ambiente que funcionou e pode ir para o GitHub.

## Ingestão (notebook 02)

O texto do livro inteiro foi extraído sem perdas e passou em todas as verificações. O notebook lê o PDF página a página com `pypdf`, limpa o texto e grava a tabela `pages`.

**Limpeza aplicada a cada página**

- Normalização de acentos (NFC), para que "Fëanor" codificado de formas diferentes seja a mesma palavra.
- Conversão de ligaduras: o PDF usa caracteres como `ﬁ` (U+FB01), que parecem "fi" na tela mas fariam "ﬁlhos" e "filhos" serem palavras diferentes na busca. O teste curto achou 55 ocorrências em 24 páginas.
- Junção de palavras hifenizadas na quebra de linha.
- Remoção de linhas que são só número de página.

**Resultado no livro inteiro**

| Verificação | Resultado |
| --- | --- |
| Páginas sem texto | 18 de 1.020 (2%); limite 10% |
| Total de palavras | 150.596; mínimo 80.000 |
| Termos-âncora | 8 de 8 encontrados (Fëanor, Silmaril, Morgoth, Valinor, Beleriand, Lúthien, Túrin, Gondolin) |
| Caracteres corrompidos | 0 depois da conversão de ligaduras |
| Cabeçalho ou rodapé repetido | nenhum |
| Sumário | páginas 5 a 8 |
| Capítulos pelo regex | 36, sem duplicatas |

Com o `CHAPTER_REGEX` definido, o 02 lista exatamente os títulos que o chunking vai usar. Sem ele, mostra linhas candidatas a título para ajudar a escrever o regex.

## Chunking (notebook 03)

O livro virou 529 chunks em 36 capítulos, sem nenhuma palavra perdida: 150.194 de 150.194. Cada chunk tem cerca de 350 palavras, com 60 de sobreposição, nunca atravessa dois capítulos e leva o nome do capítulo no início do texto.

**Como os títulos são reconhecidos**

O `CHAPTER_REGEX` foi montado a partir do próprio PDF e cobre as quatro estruturas do livro:

```
^(CAP[IÍ]TULO [IVXLC]+\b|AINULINDAL[ËE]$|VALAQUENTA$|Dos (Valar|Maiar|Inimigos)$|AKALLAB[ÊE]TH$|DOS AN[ÉE]IS DE PODER\b|GENEALOGIAS$|NOTA SOBRE A PRON[ÚU]NCIA$|GLOSS[ÁA]RIO$|AP[ÊE]NDICE$|MAPAS$)
```

| Parte | Títulos | Exemplo |
| --- | --- | --- |
| Início do livro | 5 | AINULINDALË, VALAQUENTA e as seções Dos Valar, Dos Maiar, Dos Inimigos |
| Quenta Silmarillion | 24 | CAPÍTULO VII: DAS SILMARILS E DA INQUIETAÇÃO DOS NOLDOR |
| Histórias finais | 2 | AKALLABÊTH A QUEDA DE NÚMENOR; DOS ANÉIS DE PODER E DA TERCEIRA ERA |
| Material de apoio | 5 | GENEALOGIAS, NOTA SOBRE A PRONÚNCIA, GLOSSÁRIO, APÊNDICE, MAPAS |

**Quatro armadilhas que o código trata**

1. **Título grudado no texto:** o `pypdf` extrai sem linha em branco entre o título e o parágrafo, então os títulos são detectados linha a linha.
2. **Sumário:** as páginas 5 a 8 repetem os títulos dos capítulos, que virariam capítulos vazios e duplicados. Páginas com 3 ou mais títulos são ignoradas.
3. **Título em duas linhas:** "CAPÍTULO I: DO INÍCIO DOS" + "TEMPOS" vira um nome só. Quando o regex casa só o começo do título, qualquer linha seguinte em maiúsculas entra; quando casa o título inteiro, como "NOTA SOBRE A PRONÚNCIA", só entra após palavra de ligação, e o subtítulo "CONSOANTES" fica de fora.
4. **Menções no texto:** "Akallabêth, a Derrubada" ou "AQUI TERMINA O VALAQUENTA" não viram título, porque o regex exige maiúsculas e a linha só com o nome.

**Resultado das verificações**: tudo OK, com um AVISO esperado de capítulos pequenos (VALAQUENTA com 1 chunk, Dos Maiar e Dos Inimigos com 2, CAPÍTULO IV com 2, Nota sobre a pronúncia com 2, Mapas com 1). São seções curtas de verdade. O maior capítulo é o Glossário, com 12% dos chunks.

## Índice e cadeia RAG (notebooks 04 e 05)

A cadeia responde certo e com citação quando o trecho certo é recuperado, e recusa em vez de inventar quando não é. A única falha até agora é uma pergunta que exige juntar três capítulos.

**Como funciona**

O 04 cria um índice Delta Sync sobre a tabela `chunks`, com os embeddings calculados pelo Databricks, e confere que o índice tem as mesmas linhas da tabela e que cada chunk é encontrado buscando um trecho do próprio texto. O 05 busca os 5 trechos mais relevantes (busca híbrida: vetorial mais palavra-chave), monta o prompt com eles identificados como `[c00042]` e chama o LLM com três regras: usar só os trechos, citar e recusar com a frase "Não encontrei isso nos trechos recuperados" quando faltar a resposta. Cada pergunta fica registrada no MLflow Tracing.

**Resultados**

| Pergunta | Teste (p. 153 a 176) | Livro inteiro |
| --- | --- | --- |
| Quem forjou as Silmarils? | Fëanor `[c00002]`, certo | Fëanor `[c00078]`, certo |
| Outros nomes de Túrin | Recusou: fora do trecho, certo | Turambar, Neithan, Agarwaen, com 3 citações; faltou Mormegil |
| Relação entre Lúthien e Elrond | Recusou: fora do trecho, certo | **Recusou: falha de recuperação** |
| Aniversário de Bilbo | Recusou, certo | Recusou, certo |

No teste, o trace do MLflow confirmou que o trecho `c00002` (página 158, capítulo VII) contém "fez as Silmarils": a resposta veio do texto, não da memória do modelo. As recusas sobre Túrin e Lúthien no teste mostram que o Llama 70B obedece ao contexto, mesmo conhecendo as respostas.

**Por que a pergunta sobre Lúthien e Elrond falhou**

A resposta está espalhada em três capítulos: Lúthien é mãe de Dior (cap. XIX), Dior é pai de Elwing (cap. XXII) e Elwing é mãe de Elrond (cap. XXIV). Os 5 trechos mais parecidos com a pergunta inteira não ligam as duas pontas. O modelo recusou em vez de inventar, o que é o comportamento seguro, mas é uma falha de recuperação que o notebook 06 vai medir na categoria `multi_hop`.

## Verificações automáticas e modo de teste

Cada notebook termina com um resumo de verificações. **ERRO** para a execução antes de gravar dados ruins; **AVISO** só pede que alguém confira. As funções ficam em `src/checks.py`, testáveis fora do Databricks, e os limites ficam no `00_config`.

| Notebook | O que verifica |
| --- | --- |
| 01 Setup | Modelos de embedding e LLM existem no workspace |
| 02 Ingestão | PDF no Volume (lista os arquivos se não achar); páginas sem texto; total de palavras; termos-âncora; caracteres corrompidos, com o código de cada um; cabeçalho repetido, com o padrão sugerido para remover; títulos e capítulos (só AVISO) |
| 03 Chunking | Número de capítulos; títulos duplicados; linhas longas que batem no regex; capítulos pequenos ou dominantes; chunks curtos; nenhuma palavra perdida |
| 04 Índice | Linhas no índice = linhas na tabela; auto-recuperação de chunks sorteados |
| 05 RAG | Citações da resposta estão entre os trechos recuperados |
| 06 Avaliação | Gabarito bem formado; termos esperados existem no texto da edição; juiz LLM responde |
| 07 Contrafactual | Fato falso ausente do contexto original; índice reflete a troca antes da pergunta; restauração confirmada |

**Modo de teste**

Com `PAGE_RANGE = (153, 176)` no `00_config`, o fluxo processa só essas páginas, e as tabelas e o índice ganham o sufixo `_teste`, sem sobrescrever os do livro inteiro. As verificações que só fazem sentido no livro inteiro viram informação ou AVISO, e os runs do MLflow levam a tag `modo=teste`. Foi assim que o caminho todo foi validado em 24 páginas antes de rodar as 1.020.

## Decisões tomadas

| Decisão | Por quê |
| --- | --- |
| Repositório público só com código | O livro tem direitos autorais; PDF, chunks e saídas ficam no Databricks, e os notebooks em `.py` não guardam saídas |
| Nome RAGMarillion, com dois L | Escolha do autor; o nome antigo foi trocado em todo o código, no GitHub e na pasta local |
| Verificações com dois níveis (ERRO e AVISO) | Parar só quando seguir adiante geraria dados errados sem ninguém perceber |
| Modo de teste com tabelas `_teste` separadas | Ajustar o regex por tentativa e erro sem apagar o índice do livro inteiro, que leva minutos para recriar |
| `databricks-ai-search` em vez de `databricks-vectorsearch` | O pacote antigo quebra o ambiente Serverless v6 |
| Subtítulos da Valaquenta como capítulos próprios | Cada seção trata de um grupo diferente (Valar, Maiar, Inimigos), e as citações ficam mais precisas |
| Material de apoio (Glossário, Genealogias etc.) como capítulos próprios | O Glossário ajuda nos apelidos; separado, não é citado como se fosse a história. Excluir parte dele fica para depois da avaliação |
| Fato falso do contrafactual: "Eöl" em vez de "Maglor" | Maglor é filho de Fëanor e pode aparecer na resposta por outro motivo, o que confundiria a métrica; o 07 também verifica que o fato falso não está no contexto original |
| Escolher o chunking por métrica definida antes da ablação | Evita apresentar qualquer configuração como vencedora depois de ver os resultados |

## Pendências e próximos passos

O próximo marco é medir a qualidade de forma sistemática: hoje há só 4 perguntas de teste, e o gabarito tem 11. A ordem abaixo vai do que destrava mais ao que depende dos anteriores.

- [ ] Rodar o 04 do livro inteiro e confirmar o resumo (529 linhas no índice, auto-recuperação).
- [ ] Inspecionar no MLflow os 5 trechos recuperados para Lúthien e Elrond: vieram do Glossário, das Genealogias ou só da história de Beren e Lúthien?
- [ ] Rodar o 06 com o gabarito atual, como linha de base (hit@k, MRR, recusa, Correctness e RetrievalGroundedness).
- [ ] Ampliar o gabarito para cerca de 60 perguntas, balanceadas por categoria, com `evidence_pages` (páginas do PDF onde está cada resposta) e divisão em desenvolvimento e teste.
- [ ] Acrescentar ao 06 recall@k e precisão por página, o volume de contexto e um intervalo de confiança pareado entre configurações.
- [ ] Definir a regra de decisão antes da ablação (ex.: maior Correctness com Groundedness ≥ 0,8, recusa ≥ 0,9 e contexto ≤ 1.400 palavras).
- [ ] Criar o notebook 08 de ablação: tamanho do chunk (200, 350, 500), sobreposição (0, 60, 120) e nome do capítulo no texto, com o mesmo volume de contexto.
- [ ] Atacar as perguntas de vários saltos: `TOP_K` maior, busca em etapas ou uso do Glossário.
- [ ] Rodar o 07 (contrafactual) no livro inteiro.
- [ ] Montar um Job no Databricks com o fluxo 02 → 03 → 04 → 05 → 06, com gatilho manual.

**Em aberto**

- Excluir Genealogias, Nota sobre a pronúncia e Mapas do índice? Decidir com os números do 06.
- O índice e as tabelas do modo de teste (`_teste`) podem ser apagados quando não forem mais úteis.
