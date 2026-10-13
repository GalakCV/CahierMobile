# Formato JSON de conteúdo (`cahier-content`, versão 1)

Usado pela importação (**Dados → Importar** ou `manage.py import_content`) e pela exportação de conteúdo.
Os arquivos de `seed/` são exemplos completos e reais deste formato.

## Regras da importação
- O arquivo é validado inteiro antes de gravar: campos obrigatórios, tipos, valores permitidos e coerência de
  cada questão. Todos os erros encontrados aparecem no relatório.
- A gravação acontece numa **única transação**: qualquer erro crítico desfaz tudo.
- Pela interface, primeiro há uma **simulação** (nada é gravado); só depois da confirmação os dados entram.
- **Duplicações**: códigos repetidos dentro do arquivo são recusados. Códigos que já existem no banco são
  recusados, a menos que se marque *atualizar existentes* (`--update`), o que gera nova versão das questões
  alteradas. Fontes, competências, curso e capítulos já existentes são reaproveitados — assim dá para
  acrescentar questões a um capítulo existente.
- Códigos: letras minúsculas, números, `.`, `-` e `_`.
- Campos desconhecidos geram aviso e são ignorados.

## Estrutura

```json
{
  "format": "cahier-content",
  "version": 1,
  "sources": [ { "key": "minha-fonte", "title": "…", "author": "…", "license": "CC BY 4.0",
                 "url": "https://…", "license_url": "https://…", "notes": "…" } ],
  "competencies": [ { "code": "grammaire", "name": "Gramática", "description": "…", "position": 2 } ],
  "course": { "code": "fle-a1", "title": "…", "description": "…", "reference_source": "francais-interactif" },
  "chapters": [ { … } ]
}
```

### Capítulo
| Campo | Tipo | Obrig. | Observação |
|---|---|---|---|
| code, title, theme, description | texto | sim | |
| number | inteiro | sim | único no curso |
| cefr_level | texto | | A1, A2, B1, B2 (padrão A1) |
| is_active, is_planned | booleano | | planejado = aparece só no mapa curricular |
| useful_expressions | lista de `{fr, pt}` | | |
| review_summary | lista de textos (ou texto) | | pontos de revisão |
| reference_note | texto | | relação com a referência curricular |
| objectives | lista | | `{code, description, competencies: [códigos], position}` |
| grammar_topics | lista | | `{code, title, summary, examples: [{fr, pt}], tables: [{title, rows: [[…]]}], notes, common_errors: [{wrong, right, why}]}` |
| vocabulary_topics | lista | | `{code, title, items: [{fr, pt, gender, example}]}` |
| passages | lista | | ver abaixo |
| exercises | lista | | ver abaixo |

### Texto (`passages`)
Obrigatórios: `code`, `title`, `text_type`, `body`, `difficulty` (1–5), `author`, `source` (key), `origin`.
Opcionais: `translation_pt`, `cefr_level`, `key_vocabulary` e `useful_structures` (listas de `{fr, pt}`),
`grammar_topics` e `vocabulary_topics` (códigos), `adaptation_notes` (obrigatório se `origin` = `adapted`),
`review_status`, `position`, `is_active`. Em diálogos, escreva cada fala como `Nome : fala`. A quantidade de
palavras é calculada automaticamente.

`text_type`: presentation, profile, message, email, ad, menu, schedule, invitation, form, dialogue,
description, routine, narrative, city, other.

### Questão (`exercises`)
| Campo | Obrig. | Observação |
|---|---|---|
| code, type, instruction, prompt, explanation | sim | `prompt` usa `___` para cada lacuna |
| difficulty | sim | 1 reconhecimento · 2 aplicação guiada · 3 em contexto · 4 combinação · 5 menos apoio |
| competency | sim | código da competência |
| source, origin | sim | `origin`: original, adapted, oer, public_domain, exam_inspired |
| interaction | | padrão conforme o tipo (abaixo) |
| comparison | | exact, normalized, accepted_list (padrão), regex, manual, self (padrão para texto livre) |
| accent_insensitive | | `true` só quando acentos não são o objeto do exercício |
| choices | | `{text, correct, order, match, feedback}` |
| answers | | lista de textos (o primeiro é o principal) ou `{text, blank, primary}` |
| answer | | atalho para verdadeiro/falso: `true` ou `false` gera as alternativas Vrai/Faux |
| context, translation_pt, evidence, model_answer, criteria | | `evidence` = trecho do texto que fundamenta a resposta |
| passage, reading_skill | | código do texto; habilidade: explicit, theme, character, place, time, true_false, sequence, meaning, summary, relate, inference, short, complete, intent |
| objectives, grammar_topics, vocabulary_topics | | listas de códigos |
| is_assessment | | `true` = reservada para a avaliação final do capítulo |
| related | | `[{code, kind}]`, kind: similar, variant, prerequisite, follow_up |
| cefr_level, estimated_seconds, adaptation_notes, review_status, position, is_active | | |

**Tipos (`type`) e interações aceitas** (a primeira é a padrão):

| type | interação |
|---|---|
| mc_single, true_false, select_article, select_pronoun, select_preposition, select_verb_form, identify_error, natural_response | single |
| mc_multiple | multiple |
| fill_blank, correct_sentence, transform_negative, transform_question, transform_plural, transform_gender, short_answer | text |
| conjugation, translate_fr_pt, translate_pt_fr, complete_dialogue | text ou single |
| vocabulary_review | text, single ou match |
| order_words, order_sentences | order |
| match_pairs | match |
| dialogue_comprehension | single, multiple, text ou order |
| text_interpretation | single, multiple, text, order ou match |
| guided_writing | writing |

**Verificações por interação**
- single: ≥ 2 alternativas, exatamente 1 correta, sem repetição;
- multiple: corretas e incorretas misturadas;
- order: ≥ 2 elementos; `order` de 1 a N (se omitido, vale a ordem do arquivo). A ordem de exibição é
  embaralhada automaticamente de forma estável;
- match: ≥ 2 pares, todos com `match`, sem repetição na coluna da direita;
- text: cada lacuna com ao menos uma resposta; expressões regulares válidas; em manual/self, `model_answer`;
- writing: `model_answer`, `criteria` e comparação self/manual;
- questões de texto sem `evidence` geram aviso.

### Exemplo mínimo
```json
{
  "format": "cahier-content", "version": 1,
  "chapters": [{
    "code": "ch01", "number": 1, "title": "Bonjour et bienvenue !", "theme": "…", "description": "…",
    "exercises": [{
      "code": "c1-cahier", "type": "select_article", "instruction": "Escolha o artigo.",
      "prompt": "Voilà ___ cahier.", "explanation": "cahier é masculino: un cahier.",
      "difficulty": 1, "competency": "grammaire", "origin": "original", "source": "cahier-original",
      "choices": [{"text": "un", "correct": true}, {"text": "une"}]
    }]
  }]
}
```

## Outras exportações (somente leitura)
- `cahier-progress`: preferências, tentativas (com versão respondida, resposta e nota), sessões, itens de
  revisão e domínio calculado.
- `cahier-error-notebook`: o caderno de erros com todas as colunas da tela.
- `cahier-full`: conteúdo + progresso + caderno.

Para levar o progresso para outro computador, use o **backup do banco** (arquivo `.sqlite3`), que é restaurável.
