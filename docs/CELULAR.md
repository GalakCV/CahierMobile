# Cahier no celular

O app para celular é a mesma plataforma em versão **offline**, em duas formas:

| | Android | iPhone |
|---|---|---|
| **APK** (recomendado no Android) | [Cahier.apk](https://github.com/GalakCV/CahierMobile/releases/latest/download/Cahier.apk) | — |
| **Pelo navegador** (PWA) | <https://galakcv.github.io/CahierMobile/> | <https://galakcv.github.io/CahierMobile/> |

## Android: instalar o APK

1. No celular, abra o link **Cahier.apk** acima (ou a página
   [Releases](https://github.com/GalakCV/CahierMobile/releases/latest)) e baixe o arquivo.
2. Toque no arquivo baixado. Na primeira vez, o Android pede para **permitir a instalação de apps desta
   fonte** (o navegador ou o gerenciador de arquivos): permita e volte.
3. Toque em **Instalar**. Se o Play Protect avisar que o app é desconhecido, escolha *Instalar mesmo assim*
   — o APK não vem da Play Store, mas é gerado pelo GitHub a partir deste repositório.

**Atualizar:** baixe o APK novo e instale **por cima**. O progresso é mantido (os APKs são sempre assinados
com a mesma chave). *Mais → Sobre o app* mostra a versão instalada e tem o link para a página de downloads.

**Atenção:** desinstalar o app apaga o progresso. Antes, use *Sincronizar → Exportar progresso*.

O APK é o mesmo app web empacotado num WebView, com todo o conteúdo dentro: não precisa de internet nem
tem permissão para usá-la, e não faz backup na nuvem. *Exportar progresso* abre o menu **Compartilhar** do
Android (WhatsApp, e-mail, Drive, Arquivos…); *Importar arquivo* abre o seletor de arquivos.

## Pelo navegador (PWA)

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
- `android/`: projeto Android mínimo (uma Activity com WebView, sem dependências além de `androidx.webkit`).
  Os arquivos são servidos em `https://appassets.androidplatform.net/www/` pelo `WebViewAssetLoader`, uma
  origem segura onde módulos ES, IndexedDB e a Content Security Policy funcionam como no navegador. A ponte
  `window.CahierAndroid` oferece só três funções: versão, compartilhar o arquivo exportado e a cor das barras
  do sistema conforme o tema.
- `.github/workflows/android-apk.yml`: a cada push na `main`, roda os testes, gera o conteúdo, compila e
  assina o APK, instala e abre num emulador Android 14 (`android/smoke-test.sh`) e publica em *Releases*.
  A chave de assinatura fica nos segredos `ANDROID_KEYSTORE_B64` e `ANDROID_KEYSTORE_PASSWORD`; sem eles o APK é
  compilado e testado, mas não publicado.

Para compilar o APK localmente (Android SDK e Gradle 8.11+):

```bash
python manage.py build_mobile --out android/app/src/main/assets/www
gradle -p android assembleRelease    # sem CAHIER_KEYSTORE, assina com a chave de depuração
```

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
- **Modo APK** (`mobile/tests/e2e_android.py`, ponte nativa simulada no Chromium): sem service worker nem
  aviso de offline; tela *Sobre o app* com versão e link de atualização; importar arquivo; exportar entrega o
  arquivo ao compartilhamento do Android; tema repassado às barras do sistema; nenhum erro no console.
- **APK num emulador** (Android 14, no GitHub Actions): instala, abre a tela inicial, navega até Capítulos,
  fecha e reabre, sem erros de JavaScript no log.
- **Desempenho** (Chromium com CPU 4× mais lenta, simulando um celular simples): primeira abertura em 4G
  ≈ 3,4 s; aberturas seguintes, offline, ≈ 0,6 s; responder e ver a correção, 50–95 ms. O conteúdo inteiro
  ocupa 322 KB (≈ 68 KB compactado).
