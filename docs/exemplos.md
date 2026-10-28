# RAGMarillion — perguntas, respostas e fontes

Atualizado em 28/10/2026 · velosomn

## Como ler

Cada resposta aqui é uma saída real da aplicação de terminal (`app/perguntar.py`), com a configuração padrão: busca híbrida com 5 trechos, prompt v2 e Llama 3.3 70B com temperatura 0. Quando a resposta veio de outra configuração, a seção diz.

- **Fontes:** os trechos que a resposta citou, pelo id (`c00212`), com o capítulo e as páginas do PDF.
- **Veredito:** comparação com a resposta esperada do gabarito manual (`data/eval_questions.jsonl`), quando a pergunta está nele.
- **Páginas:** são as do PDF usado no projeto, uma cópia digital de 1.020 páginas; não correspondem ao livro físico nem a outras edições ou cópias digitais.
- **Sem texto do livro:** os trechos em si não aparecem, por direitos autorais; só a resposta gerada e onde ela se apoia.

## Perguntas do gabarito manual

Das 13 perguntas de `data/eval_questions.jsonl`, 8 saíram certas (6 respostas e as 2 recusas esperadas), 3 parciais, 1 errada e 1 recusa indevida. As falhas ficam nas categorias feitas para serem difíceis: vários saltos (`q08`, `q09`), apelidos (`q04`), nomes parecidos (`q06`) e consistência (`q13`). Rodada em lote de 28/10/2026 (`python app/perguntar.py --lote data/eval_questions.jsonl`), configuração padrão.

| Pergunta | Resposta do RAG | Fontes | Veredito | Por quê |
| --- | --- | --- | --- | --- |
| `q01` Quem forjou as Silmarils? | Fëanor forjou as Silmarils [c00078]. | `c00078` cap. VII, p. 158–160 | Certa | Fëanor, como esperado |
| `q02` Quem destruiu as Duas Árvores de Valinor? | Melkor e Ungoliant destruíram as Duas Árvores de Valinor [c00092]. | `c00092` cap. VIII, p. 183–185 | Certa | Melkor e Ungoliant, como esperado |
| `q03` Qual era a cidade escondida governada por Turgon? | A cidade escondida governada por Turgon era Gondolin, também conhecida como Ondolindë, ou a Rocha da Música da Água, e como a Rocha Oculta [c00172]. | `c00172` cap. XV, p. 330–332 | Certa | Gondolin; os outros nomes também são do livro |
| `q04` Que outros nomes Túrin usou ao longo da vida? | Túrin usou os seguintes nomes ao longo da vida: Agarwaen, filho de Úmarth, que significa “o Sujo de Sangue, filho do Infeliz” [c00305], e Turambar, que em alto-élfico significa “Senhor do Destino” [c00317]. Além disso, ele também foi conhecido como Mormegil [c00307] e Túrin, filho de Húrin [c00307]. | `c00305` cap. XXI, p. 589–591; `c00307` cap. XXI, p. 593–595; `c00317` cap. XXI, p. 612–613 | Parcial | Cita Agarwaen, Mormegil e Turambar; falta Neithan. “Túrin, filho de Húrin” não é outro nome |
| `q05` Quem era chamado de Mormegil, a Espada Negra? | Túrin era chamado de Mormegil, a Espada Negra [c00306]. | `c00306` cap. XXI, p. 591–593 | Certa | Túrin, como esperado |
| `q06` Qual rei dos Noldor morreu na Nirnaeth Arnoediad? | Fingon, o Rei Supremo dos Noldor após a morte de seu pai, morreu na Nirnaeth Arnoediad, mas não especificamente na batalha, e sim nas mãos de Gothmog [c00477]. Já Fingolfin, o Rei Supremo dos Noldor, morreu em combate homem a homem contra Morgoth [c00477], mas não na Nirnaeth Arnoediad, e sim em Angband [c00217]. | `c00477` Glossário, p. 918–920; `c00217` cap. XVIII, p. 417–419 | Parcial | Acerta Fingon e Gothmog, mas se contradiz (“não especificamente na batalha”); a fonte é o glossário, não o capítulo XX |
| `q07` Quem era o filho de Eöl e Aredhel? | O filho de Eöl e Aredhel era Maeglin, também conhecido como Lómion, que significa Filho do Crepúsculo [c00185]. | `c00185` cap. XVI, p. 356–357 | Certa | Maeglin; Lómion também está no livro |
| `q08` Qual é o parentesco entre Lúthien e Elrond? | Lúthien é antepassada de muitos nos quais os eldar ainda vêem o semblante de Lúthien, e Elrond é um desses, pois é filho de Eärendil, que por sua vez é filho de Tuor e Idril, e neto de Beren e Lúthien [c00269]. | `c00269` cap. XIX, p. 518–520 | Errada | Não diz bisavó, pula Dior e Elwing e faz de Eärendil neto de Beren e Lúthien, o que é Elwing. A busca não trouxe os elos |
| `q09` De onde veio a Silmaril que Eärendil levou ao navegar até Valinor? | A Silmaril que Eärendil levou ao navegar até Valinor veio de Elwing, que a tinha ao peito quando se jogou ao mar e foi salva por Ulmo, tomando a forma de uma grande ave branca [c00364]. Elwing a obtivera após a destruição dos Portos do Sirion e o cativeiro de seus filhos [c00364]. | `c00364` cap. XXIV, p. 701–703 | Parcial | Acerta Elwing, mas ela já tinha a Silmaril e fugiu com ela no ataque aos Portos; faltam Beren, Lúthien e Dior |
| `q10` Qual é a data de aniversário de Bilbo Bolseiro? | Não encontrei isso nos trechos recuperados. | nenhuma | Recusa certa | O livro não tem a resposta |
| `q11` Qual era o nome do pônei de Sam? | Não encontrei isso nos trechos recuperados. | nenhuma | Recusa certa | O livro não tem a resposta |
| `q12` Quem criou os anéis de poder? | Os anéis de poder foram feitos pelos elfos, com a orientação de Sauron [c00420]. Além disso, os Três Anéis (Narya, Nenya e Vilya) foram forjados somente por Celebrimbor [c00421]. | `c00420` Dos anéis de poder, p. 807–809; `c00421` p. 809–811 | Certa | Elfos com orientação de Sauron; os Três só por Celebrimbor |
| `q13` Quem criou os nove anéis de poder que foram dados aos homens? | Não encontrei isso nos trechos recuperados. | nenhuma | Recusa indevida | O `c00421`, recuperado, diz que Sauron deu nove anéis aos homens e participou da confecção: dava para responder em parte |

As respostas esperadas estão no gabarito. Em `q06`, `q08`, `q09` e `q13` a busca não trouxe o trecho narrativo que tinha a resposta inteira.

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
| v2 | “Não encontrei isso nos trechos recuperados.” | nenhuma | Recusa indevida: o c00421, recuperado, tinha parte da resposta |

A busca trouxe `c00422`, `c00457` (glossário), `c00421`, `c00426` e `c00427`. O `c00421` diz que Sauron deu nove anéis aos homens e que tinha participado da confecção deles: dava para responder em parte, e a recusa do v2 é indevida. O `c00420`, que conta a confecção pelos artífices de Eregion, não veio. Com “nove” por extenso e “aos homens” (a `q13` do lote), a busca muda, mas o `c00421` vem de novo e o v2 recusa do mesmo jeito.
