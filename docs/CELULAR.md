# Cahier no celular

O app para celular é a mesma plataforma em versão **offline e instalável** (PWA): Android e iPhone, sem loja.

**Endereço:** <https://galakcv.github.io/Cahier/>

## Instalar

| Android (Chrome) | iPhone (Safari) |
|---|---|
| Abra o endereço → menu **⋮** → **Instalar app** (ou “Adicionar à tela inicial”). | Abra o endereço → **Compartilhar** → **Adicionar à Tela de Início**. |

Depois da primeira abertura com internet, tudo fica guardado no aparelho e o app funciona **sem conexão**
(ônibus, metrô, avião). Quando houver internet, versões novas são baixadas sozinhas e o app mostra
“Nova versão disponível · Atualizar”.

No iPhone, use o app pelo ícone da tela inicial: o Safari pode apagar dados de sites abertos só no
navegador depois de alguns dias sem uso, mas não os de apps instalados. Em *Mais → Instalar e usar offline*
há um botão para pedir ao navegador que proteja os dados.

## O que tem

Tudo o que é de estudo no computador: os 4 capítulos com explicações, vocabulário e textos; os 27 tipos de
exercício; correção com as mesmas regras (acentos, variantes, expressões regulares); modo prática e avaliação;
revisão espaçada; caderno de erros; produção escrita com autoavaliação; domínio por capítulo, objetivo,
gramática, vocabulário e competência; marcar e sinalizar questões.

Pensado para o trajeto:
- **Sessões rápidas** de 5, 10 ou 20 questões, a um toque da tela inicial.
- **Teclado de acentos** acima do teclado do celular, com botão **OK** para enviar sem fechar o teclado.
- **Texto e perguntas na mesma tela** (o texto pode ser recolhido).
- Botões grandes no alcance do polegar, tema escuro e texto maior em *Preferências*.
- Sessões interrompidas continuam de onde pararam, mesmo depois de fechar o app.

O que fica só no computador: painel administrativo, cadastro e importação de conteúdo, backup do banco.

## Sincronizar com o computador

O celular e o computador guardam o progresso separadamente. Para juntar, troque um arquivo:

1. **Celular → computador:** no celular, *Mais → Sincronizar → Exportar progresso*. Envie o arquivo para
   você mesmo (e-mail, Drive, WhatsApp…). No computador, *Dados e backup → Importar progresso do celular*.
2. **Computador → celular:** no computador, *Dados e backup → Baixar progresso para o celular*. No celular,
   *Sincronizar → Importar arquivo*.

Regras da mescla (iguais nos dois lados):
- cada resposta tem um identificador único: as novas são somadas, as repetidas são ignoradas — importar o
  mesmo arquivo duas vezes não duplica nada;
- respostas nunca são alteradas; só a autoavaliação de um texto é atualizada, se a do arquivo for mais recente;
- marcações para revisão, avaliações finais de capítulo e problemas sinalizados também vão juntos;
- depois da mescla, a fila de revisão e o domínio são **recalculados a partir do histórico completo**;
- o computador cria um backup automático antes de cada importação.

Formato do arquivo (`cahier-sync`, versão 1): ver [FORMATO_JSON.md](FORMATO_JSON.md#sincronização-cahier-sync).

## Privacidade

O app é um site estático: não tem servidor, conta, telemetria nem chamadas a terceiros (há uma Content
Security Policy que bloqueia qualquer recurso externo). As respostas ficam no armazenamento do navegador
(IndexedDB) do próprio aparelho e só saem dele quando você exporta o arquivo de sincronização.

## Como é feito

- `mobile/src/`: HTML, CSS e JavaScript sem dependências nem etapa de compilação (módulos ES).
- `mobile/src/js/core/`: correção, domínio, revisão espaçada e seleção de questões — tradução linha a linha
  de `learning/grading.py`, `mastery.py`, `review.py` e `sessions.py`.
- `python manage.py build_mobile`: gera `mobile/dist/` com o conteúdo atual do banco (`content.json`) e um
  service worker cuja versão muda quando qualquer arquivo muda.
- `.github/workflows/mobile-pages.yml`: a cada push na `main`, roda os testes, gera o app a partir do
  conteúdo inicial e publica no GitHub Pages.

Para ver o app com o **seu** conteúdo (por exemplo, questões que você cadastrou no painel), rode
`manage.py build_mobile` e sirva `mobile/dist/` (ou publique-o).

## Verificação

- **Paridade Python ↔ JavaScript** (`tests/test_mobile_parity.py`): mais de 3 000 respostas sobre todas as
  questões (certas, erradas, sem acento, com pontuação, em maiúsculas…), 120 históricos aleatórios de domínio
  e 80 sequências de revisão dão resultados idênticos nos dois lados.
- **Ponta a ponta no celular** (`mobile/tests/e2e_mobile.py`, Chromium em tela de 390 px, toque e modo
  offline): abrir e recarregar sem internet; sessão rápida; acerto e erro com explicação; marcar; interromper,
  recarregar e retomar; 80 questões de todos os capítulos e formas de resposta corrigidas como certas com o
  gabarito; interpretação de texto; teclado de acentos; revisões; caderno de erros; avaliação final aprovada;
  exportação; importação do progresso do computador sem duplicar; preferências mantidas; nenhum erro no console.
- **Sincronização cruzada:** o arquivo exportado pelo celular foi importado no Django (105 respostas,
  marcação e avaliação; capítulo 1 aparece como concluído) e o arquivo do computador foi importado no celular.
- **Desempenho** (Chromium com CPU 4× mais lenta, simulando um celular simples): primeira abertura em 4G
  ≈ 3,4 s; aberturas seguintes, offline, ≈ 0,6 s; responder e ver a correção, 50–95 ms. O conteúdo inteiro
  ocupa 322 KB (≈ 68 KB compactado).
