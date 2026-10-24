# Discussão: como avaliar o RAG

Atualizado em 24/10/2026 · velosomn

A falha na pergunta sobre Lúthien e Elrond levou a quatro conclusões sobre como evoluir o RAG sem perseguir casos isolados:

1. **A falha é de recuperação, não de geração.** Os 5 trechos vieram do mesmo capítulo (XIX), e aumentar o `TOP_K` sozinho provavelmente não resolve.
2. **O risco de overfitting está no processo de escolha**, não nas técnicas: casos isolados geram hipóteses, e a decisão vem de uma métrica agregada em perguntas que não foram usadas para criar as técnicas.
3. **A métrica global existe** (Recall@k, nDCG@k, juiz `RetrievalSufficiency`), mas só é global se o conjunto de perguntas for grande e representativo: cerca de 200 sintéticas mais 60 escritas à mão.
4. **Neste livro, um LLM sozinho já sabe muito.** O valor do RAG está na citação verificável, nos detalhes que o modelo não lembra e, principalmente, em documentos que ele nunca viu. A avaliação deve incluir uma linha de base sem contexto para medir isso.

## Diagnóstico da falha

Para "Qual é a relação entre Lúthien e Elrond?", os 5 trechos recuperados vieram todos do CAPÍTULO XIX: DE BEREN E LÚTHIEN, e nenhum cita Dior, Elwing ou Elrond. O modelo recusou em vez de inventar.

| Trecho | Página | Nota da busca | Assunto |
| --- | --- | --- | --- |
| `c00268` | 517 | 0,93 | Lúthien diante de Mandos |
| `c00234` | 450 | 0,91 | Beren encontra Lúthien |
| `c00235` | 452 | 0,87 | Beren levado ao trono de Thingol |
| `c00236` | 454 | 0,83 | Thingol e o anel de Felagund |
| `c00257` | 496 | 0,82 | Carcharoth diante de Angband |

A resposta exige três capítulos: Lúthien é mãe de Dior (cap. XIX), Dior é pai de Elwing (cap. XXII) e Elwing é mãe de Elrond (cap. XXIV). Dois fatores levaram a busca a ficar no XIX:

- **"Lúthien" domina a pergunta.** O capítulo XIX tem cerca de 80 páginas e uns 40 chunks, quase todos com o nome dela; "Elrond" aparece em pouquíssimos.
- **Os 5 lugares ficam com trechos repetitivos.** Os cinco falam de Lúthien, Beren e Thingol, sem nenhuma informação nova entre eles.

Por isso, aumentar o `TOP_K` de 5 para 10 provavelmente traria mais 5 trechos do mesmo capítulo.

## Estratégias de busca possíveis

Três técnicas gerais de RAG atacam o problema. Nenhuma foi implementada ainda; a proposta é criá-las como opções no `00_config` (`RETRIEVAL_STRATEGY`), com o padrão continuando `simples`, e escolher pela avaliação.

| Estratégia | Como funciona | Custo | Limitação |
| --- | --- | --- | --- |
| `simples` (atual) | Os 5 trechos mais parecidos com a pergunta | 1 busca | Trechos repetitivos de um mesmo capítulo |
| `diversa` | Busca os 20 melhores e escolhe 5 com no máximo 2 por capítulo | 1 busca, sem LLM extra | Abre espaço para outros capítulos, mas não garante que sejam os certos; pode tirar um segundo trecho bom do capítulo certo |
| `por_nome` | Uma busca por nome próprio da pergunta, mais a pergunta inteira, e junta os resultados | 2 a 3 buscas | Traz as pontas (Lúthien, Elrond), mas pode faltar o elo do meio (Dior e Elwing) |
| `em_etapas` | O LLM lê os primeiros trechos, percebe o que falta e pede uma nova busca | 2 a 3 chamadas ao LLM | Mais lenta e cara, mas é a única que fecha uma cadeia de três gerações com segurança |

O Glossário do livro deve ajudar as três, porque tem entradas que ligam as gerações; isso ainda precisa ser confirmado.

## Overfitting: onde está o risco

A dúvida levantada foi: criar uma estratégia a cada falha não é ajustar o sistema a casos específicos? Seria, se o critério para adotar uma técnica fosse "ela conserta a pergunta da Lúthien". Diversidade, decomposição da pergunta e busca em etapas são técnicas gerais de RAG; o risco está em como se escolhe entre elas.

**Regras adotadas**

1. Casos individuais servem para gerar hipóteses ("a resposta está espalhada em vários capítulos"), nunca para aprovar uma mudança.
2. Um cardápio pequeno de técnicas gerais, sem inventar uma nova a cada falha.
3. A decisão vem de uma métrica agregada, com a regra escrita antes de comparar.
4. Escolha no conjunto de desenvolvimento; o conjunto de teste confirma uma vez só.
5. Uma mudança que conserta um caso e piora três é rejeitada pelo número.
6. Empate dentro do ruído favorece a opção mais simples ou mais barata.

Uma técnica nova no futuro entra como mais uma linha da tabela de comparação, não como mais um caso a olhar.

## Métricas globais de recuperação

Com um gabarito que diga onde está a resposta de cada pergunta (o chunk ou a página), a qualidade da busca vira um número calculado sobre todas as perguntas. O hit@k atual, que só procura um termo esperado no texto, é uma aproximação fraca: "Fëanor" aparece em dezenas de capítulos.

| Métrica | O que mede | Papel |
| --- | --- | --- |
| Recall@k | Fração das perguntas em que o trecho com a resposta veio entre os k recuperados | Principal: o LLM não responde o que não recebeu |
| Recall completo@k | Fração das perguntas de vários saltos em que todos os trechos necessários vieram | Pega casos como Lúthien e Elrond |
| nDCG@k | Recall com peso pela posição: o trecho certo em 1º vale mais que em 5º | Desempate entre configurações |
| Precisão@k | Quantos dos k trechos são úteis | Mede a poluição do contexto |
| `RetrievalSufficiency` (juiz LLM do MLflow 3) | Se os trechos recuperados bastavam para chegar à resposta esperada | Não exige marcar páginas; cobre perguntas com várias respostas certas |

A escolha é uma tabela única: cada linha uma combinação de chunking e estratégia de busca; as colunas Recall@5, Recall completo@5, nDCG@10 e palavras de contexto; o resultado mostrado também por categoria de pergunta, porque um número global pode esconder que uma estratégia ajuda os saltos e piora as perguntas simples.

## Perguntas sintéticas

Uma métrica é tão representativa quanto as perguntas em que é medida, e 11 perguntas escolhidas à mão dão números anedóticos. A proposta é gerar cerca de 200 perguntas a partir de chunks sorteados no livro inteiro, mais cerca de 60 escritas à mão.

**Quem gera e como.** Um LLM, num notebook (`06a_gerar_gabarito`), recebe só um chunk sorteado e escreve uma pergunta que aquele trecho responde e a resposta, usando apenas o trecho. O chunk e a página de origem vêm do sorteio, não do LLM, e são o que permite calcular o Recall@k automaticamente. De preferência, um modelo diferente do que responde no RAG, se houver outro em Serving, para a avaliação não ficar otimista.

```json
{"id": "s017", "category": "sintetica",
 "question": "Onde Fëanor guardou as Silmarils depois de ser banido de Tirion?",
 "expected_response": "Na fortaleza de Formenos.",
 "expected_terms": ["Formenos"],
 "source_chunk": "c000xx", "evidence_pages": [1xx]}
```

| Risco | Exemplo | Controle |
| --- | --- | --- |
| Resposta que não está no trecho | O modelo responde de memória | Descartar se os termos da resposta não aparecem no chunk |
| Pergunta ambígua | "O que ele fez depois disso?" | Pedir perguntas com nomes; descartar as com pronomes soltos |
| Muitas respostas certas | "Quem é Morgoth?", que dezenas de trechos respondem | Usar também o juiz `RetrievalSufficiency`, que avalia se o contexto basta |
| Fácil demais | Copia frases do trecho, e a busca por palavra-chave acerta sempre | Pedir paráfrase e manter as perguntas escritas à mão no conjunto |

**Revisão humana por amostra:** conferir cerca de 30 das 200 dá a taxa de erro do conjunto e, com ela, quanto confiar em diferenças pequenas.

**Onde guardar:** as perguntas sintéticas derivam do texto do livro, então ficam numa tabela no Databricks, não no repositório público. O gabarito à mão, com respostas curtas e factuais, pode continuar no GitHub.

## Por que um RAG e não só o LLM

Neste livro, um LLM sozinho já responderia bem à maioria das perguntas. O Silmarillion é famoso e muito discutido na internet, e os modelos aprenderam esses fatos no treinamento. A própria pergunta sobre Lúthien e Elrond veio no gabarito inicial, escrita por um LLM a partir do que ele já sabia, sem ler o PDF. Mesmo assim, há três motivos para o RAG:

1. **A memória do LLM não é verificável.** Ele responde com a mesma confiança quando sabe e quando inventa, e nos detalhes costuma errar sem avisar: troca nomes parecidos, mistura com O Senhor dos Anéis, com outros livros póstumos de Tolkien ou com as séries de TV. O RAG responde "Fëanor [c00078]", e qualquer um confere o trecho da página 158.
2. **O RAG é para o que o LLM nunca leu.** O valor real aparece em contratos, políticas internas, normas, documentos recentes e dados privados, em que não existe a opção de perguntar direto ao modelo. O Silmarillion funciona aqui como campo de treino: como as respostas são conhecidas, dá para verificar o sistema; e como o modelo sabe de memória, dá para testar se ele usa o contexto ou a memória, que é o que o notebook 07 (contrafactual) mede.
3. **Ler o livro inteiro a cada pergunta não cabe.** São cerca de 150 mil palavras, algo como 200 mil tokens, acima dos 128 mil do Llama 3.3. O RAG manda cerca de 1.750 palavras por pergunta.

**Linha de base sem contexto.** A pergunta é empírica e cabe no notebook 06: as mesmas perguntas, sem busca, avaliadas pelos mesmos juízes. A expectativa é que o LLM sozinho empate ou ganhe nas perguntas famosas, como a de Lúthien e Elrond hoje, e perca nos detalhes; só o RAG cita a fonte e pode ser testado pelo contrafactual. O resultado mostra onde o RAG agrega valor, em vez de assumir que sempre agrega.

## Decisões e próximos passos

Nenhuma mudança na busca foi feita: a pergunta sobre Lúthien e Elrond continua sendo recusada. Está em aberto qual caminho seguir.

| Caminho | O que inclui | Prós e contras |
| --- | --- | --- |
| A. Medir antes | Gerar as perguntas sintéticas; acrescentar ao 06 Recall@k, nDCG, o juiz `RetrievalSufficiency` e a linha de base sem contexto; depois implementar as estratégias como opções comparáveis | Escolha sólida, sem overfitting; a pergunta da Lúthien só melhora depois de tudo isso |
| B. Implementar já, decidir depois | Criar `diversa`, `por_nome` e `em_etapas` no `00_config`, com o padrão `simples`, e testar a pergunta da Lúthien com cada uma | Mostra logo se alguma resolve o caso; a escolha definitiva continua sendo pela métrica |

Nos dois caminhos, nenhuma estratégia vira padrão por ter acertado uma pergunta isolada.

- [ ] Escolher entre os caminhos A e B.
- [ ] Criar o notebook `06a_gerar_gabarito` (sorteio, geração, filtros, tabela no Databricks, amostra para revisão).
- [ ] Revisar cerca de 30 perguntas sintéticas e registrar a taxa de erro.
- [ ] Acrescentar ao 06 Recall@k, Recall completo@k, nDCG@k, `RetrievalSufficiency` e a linha de base sem contexto.
- [ ] Escrever a regra de decisão no `00_config` antes de comparar estratégias e chunkings.
