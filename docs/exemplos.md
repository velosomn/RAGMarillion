# RAGMarillion — perguntas, respostas e fontes

Atualizado em 28/10/2026 · velosomn

## Como ler

Cada resposta aqui é uma saída real da aplicação de terminal (`app/perguntar.py`), com a configuração padrão: busca híbrida com 5 trechos, prompt v2 e Llama 3.3 70B com temperatura 0. Quando a resposta veio de outra configuração, a seção diz.

- **Fontes:** os trechos que a resposta citou, pelo id (`c00212`), com o capítulo e as páginas do PDF.
- **Veredito:** comparação com a resposta esperada do gabarito manual (`data/eval_questions.jsonl`), quando a pergunta está nele.
- **Páginas:** são as do PDF usado no projeto, uma cópia digital de 1.020 páginas; não correspondem ao livro físico nem a outras edições ou cópias digitais.
- **Sem texto do livro:** os trechos em si não aparecem, por direitos autorais; só a resposta gerada e onde ela se apoia.

## Perguntas do gabarito manual

Pendente: as 13 perguntas de `data/eval_questions.jsonl` serão respondidas com `python app/perguntar.py --lote data/eval_questions.jsonl` e comentadas aqui.

## Perguntas feitas na aplicação

Cinco perguntas feitas à mão no terminal, em 28/10/2026. As três abertas recebem respostas corretas e citadas, mas incompletas; nas dos anéis, a resposta muda com o prompt e com o que a busca traz.

### “Sobre o que fala este livro?”

Prompt v2.

> O livro fala sobre a história da Terra-média, desde a Música dos Ainur, com a qual o mundo começou, até a passagem dos Portadores do Anel saindo dos Portos de Mithlond, no final da Terceira Era [c00003]. Ele inclui a narrativa da Primeira Era, com a história dos elfos e homens, e também aborda a mitologia e a poesia da Terra-média [c00001]. Além disso, o livro contém várias obras curtas, como o Valaquenta, o Quenta Silmarillion, o Ainunlidalë, o Akallabêth e Dos anéis de poder [c00002].

| Fonte | Capítulo | Páginas |
| --- | --- | --- |
| `c00003` | Início (prefácio) | 14–16 |
| `c00001` | Início (prefácio) | 11–13 |
| `c00002` | Início (prefácio) | 13–14 |

**Veredito:** correta e apoiada, mas descreve a estrutura do livro, não o enredo. Funcionou porque o prefácio descreve o livro. “Ainunlidalë” é erro de grafia do PDF (Ainulindalë).

### “Quais são os principais conflitos do livro?”

Prompt v2.

> Os principais conflitos do livro incluem a guerra entre os Valar e Melkor, a discórdia dentro da Casa de Finwë, especialmente entre Fëanor e os filhos de Indis, e a luta contra a destruição causada por Melkor [c00054], [c00020], [c00075]. Além disso, há o conflito interno de Melkor, que é motivado pela inveja e pelo ódio [c00020], [c00075].

| Fonte | Capítulo | Páginas |
| --- | --- | --- |
| `c00054` | III: Da chegada dos elfos e do cativeiro de Melkor | 111–113 |
| `c00020` | Dos Valar | 47–49 |
| `c00075` | VI: De Fëanor e da libertação de Melkor | 152–154 |

Recuperados e não citados: `c00003` e `c00002`, do prefácio.

**Veredito:** correta e citada, mas incompleta: tudo vem das primeiras 154 páginas. Faltam o juramento de Fëanor, Alqualondë, as guerras de Beleriand, Númenor e os anéis.

### “Quais foram as grandes batalhas dos Noldor contra Morgoth em Beleriand?”

Prompt v2.

> As grandes batalhas mencionadas nos trechos são: Dagor-nuin-Giliath, a Batalha-sob-as-estrelas [c00142]; Dagor Aglareb, a Batalha Gloriosa [c00156]; Dagor Bragollach, a Batalha das Chamas Repentinas [c00211, c00212]. Além disso, também é mencionada a Guerra da Ira [c00370].

| Fonte | Capítulo | Páginas |
| --- | --- | --- |
| `c00142` | XIII: Da volta dos Noldor | 276–278 |
| `c00156` | XIII: Da volta dos Noldor | 302–304 |
| `c00211` | XVIII: Da ruína de Beleriand e da queda de Fingolfin | 406–408 |
| `c00212` | XVIII: Da ruína de Beleriand e da queda de Fingolfin | 408–410 |
| `c00370` | XXIV: Da viagem de Eärendil e da Guerra da Ira | 712–714 |

**Veredito:** incompleta. Faltou a maior, a Nirnaeth Arnoediad (capítulo XX), embora o `c00212` fale na “quarta das grandes batalhas”, o que indica uma quinta.

### “Quem criou os anéis de poder?”

Prompt v1 (antes do v2 existir). Está no gabarito como `q12`.

> Os Anéis de Poder foram criados pelos artífices de Ost-in-Edhil, mas sob a influência e orientação de Sauron [c00420]. Além disso, os Três Anéis (Narya, Nenya e Vilya) foram feitos por Celebrimbor, sem a participação de Sauron [c00421].

| Fonte | Capítulo | Páginas |
| --- | --- | --- |
| `c00420` | Dos anéis de poder e da Terceira Era | 807–809 |
| `c00421` | Dos anéis de poder e da Terceira Era | 809–811 |

**Veredito:** correta; bate com a resposta esperada.

### “Quem criou os 9 anéis de poder que foram dados para os homens?”

Está no gabarito como `q13`. Esperado: os artífices élficos de Eregion, com a participação de Sauron, que depois os distribuiu aos homens.

| Prompt | Resposta | Fonte | Veredito |
| --- | --- | --- | --- |
| v1 | “Sauron criou os 9 anéis de poder que foram dados para os homens [c00422].” | `c00422`, p. 811–812 | Errada: o trecho diz o que os anéis fizeram aos homens, não quem os fez |
| v2 | “Não encontrei isso nos trechos recuperados.” | nenhuma | Não exagera, mas recusa |

A busca trouxe `c00422`, `c00457` (glossário), `c00421`, `c00426` e `c00427`, mas não o `c00420`, onde está a confecção dos anéis. A recusa do v2 é a resposta honesta para o que chegou ao modelo; o erro real está na busca.
