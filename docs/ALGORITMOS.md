# Algoritmos: correção, domínio e revisão espaçada

Este documento descreve exatamente o que o código faz (`learning/grading.py`, `learning/mastery.py`,
`learning/review.py`, `learning/sessions.py`). A página **Progresso** mostra um resumo para o estudante.

## 1. Correção

### Formas de resposta
| Interação | Correção |
|---|---|
| Escolha única | Correta se a alternativa marcada é a correta. Alternativas podem ter um comentário específico (ex.: por que « et » não é « est »). |
| Múltipla seleção | Nota = (acertos − marcações erradas) ÷ total de corretas, mínimo 0. Tudo certo = correta; nota > 0 = parcial. |
| Ordenação | Correta se a sequência é a esperada **ou** se o texto montado coincide com uma ordem alternativa cadastrada como resposta aceita. Senão, nota = posições certas ÷ total (≥ 0,5 = parcial). |
| Relacionar pares | Nota = pares certos ÷ total (todos = correta; ≥ 0,5 = parcial). |
| Resposta digitada | Ver modos abaixo. Várias lacunas: nota = lacunas certas ÷ total. |
| Texto livre | Fica pendente: o estudante compara com a resposta-modelo e marca os critérios atendidos (nota = critérios ÷ total) ou registra correção manual. |

### Modos de comparação (respostas digitadas)
- **exato** — igualdade com uma resposta cadastrada; só unifica tipos de apóstrofo e tira espaços nas pontas.
- **normalizado** — ignora maiúsculas, espaços extras e pontuação (`. , ; : ! ? « » " ( ) …`), unifica apóstrofos,
  remove espaços em volta de apóstrofo e hífen (`j' ai` → `j'ai`, `est - ce` → `est-ce`), aceita `oe`/`ae` por `œ`/`æ`.
  **Mantém os acentos.** Compara só com as respostas *principais*.
- **lista de respostas aceitas** — a mesma normalização, comparando com todas as variantes.
- **expressão regular** — a resposta normalizada (minúsculas, sem pontuação) precisa casar inteira com a expressão.
  A tela mostra a resposta-modelo, nunca a expressão.
- **correção manual / autoavaliação** — a resposta é guardada e avaliada depois.

**Acentos.** Se a resposta só difere nos acentos, ela é *incorreta* com o aviso “confira os acentos”, a menos que a
questão tenha **tolerar acentos** ligado; nesse caso é correta, com o aviso de que a grafia usa acento.

## 2. Domínio (0–100%)

Calculado para: geral, cada capítulo, objetivo, tópico gramatical, tema de vocabulário e competência
(vocabulário, gramática, conjugação, ortografia, leitura, interpretação, tradução, escrita). Considera somente
questões ativas do escopo e tentativas já avaliadas (textos pendentes não contam).

```
domínio = max(0, min(teto, precisão × confiança) − penalidade)
```

**Precisão** — média ponderada das notas (0 a 1) de todas as tentativas do escopo. Peso de cada tentativa:
- dificuldade: 0,6 · 0,8 · 1,0 · 1,2 · 1,4 (níveis 1 a 5);
- recência: 0,9 elevado à posição a partir da mais recente (mínimo 0,2) — o desempenho recente pesa mais;
- velocidade: × 0,85 se o tempo de resposta passou do dobro do estimado;
- retenção: × 1,3 se for um acerto ao menos 3 dias depois da tentativa anterior da mesma questão.

**Confiança** = 0,5 × cobertura + 0,25 × variedade + 0,25 × evidência, limitada a 0,3 + 0,7 × evidência.
- cobertura = questões diferentes respondidas ÷ questões do escopo;
- variedade = tipos de exercício diferentes respondidos ÷ min(5, tipos disponíveis);
- evidência = min(1, tentativas avaliadas ÷ 12).

**Teto** = 90% enquanto não houver prova de retenção; 100% depois.
**Penalidade** = 5 pontos por questão cujas duas tentativas mais recentes foram erros (máx. 20).

Consequências: uma resposta certa isolada nunca passa de ~36%; dominar um capítulo exige responder boa
parte dele, com variedade, e acertar de novo após alguns dias. Níveis exibidos: Inicial (< 20),
Em desenvolvimento (20–49), Bom (50–74), Forte (75–89), Dominado (≥ 90).

### Estado do capítulo
1. **Não iniciado** — nenhuma tentativa.
2. **Concluído** — avaliação final feita com 70% ou mais.
3. **Revisão necessária** — 3+ erros do capítulo vencidos na fila de revisão, ou acerto abaixo de 50% nas
   últimas duas semanas (com ao menos 5 respostas).
4. **Apto para avaliação** — domínio ≥ 60% e ao menos 50% das questões respondidas.
5. **Em andamento** — nos demais casos.

## 3. Revisão espaçada

Cada questão respondida ganha um item de revisão com etapa de 0 a 4 e intervalos base de **1, 3, 7, 14 e 30 dias**.

| Evento | Efeito |
|---|---|
| Primeira resposta certa | etapa 2 (7 dias) — manutenção |
| Primeira resposta errada/parcial | etapa 0 (1 dia), entra no caderno de erros |
| Acerto | avança uma etapa (máx. 4) |
| Parcial | recua uma etapa e conta um erro |
| Erro | recua duas etapas (mín. 0) e conta um erro |
| Erros repetidos | intervalo ÷ (1 + 0,25 × (erros − 1)), até 4 erros, mínimo 1 dia |
| Marcar para revisão | fica pendente imediatamente até ser acertada |

Na etapa 4 a questão continua voltando a cada 30 dias (dominadas também são revisadas).

**Prioridade na fila** = dias de atraso + 1,5 × erros (até 5) + 3 se marcada + (100 − domínio da competência) ÷ 50.
A sessão de revisão usa só itens vencidos, em ordem de prioridade, sem colocar juntas questões marcadas como
“muito semelhantes” ou “variantes” e limitando a concentração num mesmo tópico gramatical.

**Caderno de erros** — estado de recuperação:
- *Erro recente*: a última resposta foi errada ou parcial;
- *Em revisão*: acertou a última, mas ainda não duas seguidas;
- *Melhorando*: dois acertos seguidos;
- *Superado*: três acertos seguidos e intervalo de pelo menos 14 dias.

## 4. Montagem das sessões de prática
1. Filtra por capítulo, tema (tópico gramatical ou de vocabulário), competência e dificuldade. As questões de
   avaliação final ficam fora da prática.
2. Pontua: +3 se nunca respondida, +2 por erro registrado (até 3), + fragilidade da competência, + um sorteio.
3. Escolhe as melhores sem semelhantes juntas e com no máximo metade da sessão num mesmo tópico.
4. Apresenta em ordem crescente de dificuldade, mantendo juntas as perguntas de um mesmo texto.
