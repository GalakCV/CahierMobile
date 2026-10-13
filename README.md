# Cahier — exercícios de francês (A1), no seu computador

Plataforma web local para consolidar o nível **A1** de francês com atividades **exclusivamente escritas**:
vocabulário, gramática, conjugação, ortografia, leitura, interpretação de texto, tradução contextualizada
e produção escrita guiada.

Tudo roda no seu computador: um servidor Django em `127.0.0.1:8000`, acessado pelo navegador em
**http://localhost:8000**. O banco SQLite, o progresso e os backups ficam na pasta `data/`. Não há
telemetria, contas, senhas nem chamadas externas.

---

## Instalação no Windows

Pré-requisito: **Python 3.10 ou mais recente** ([python.org/downloads](https://www.python.org/downloads/)).
Na instalação do Python, marque **“Add python.exe to PATH”**.

1. Descompacte a pasta `cahier` onde quiser (por exemplo, `Documentos\cahier`).
2. Dê dois cliques em **`Instalar.bat`**
   (ou, no PowerShell: `powershell -ExecutionPolicy Bypass -File setup.ps1`).
   O script cria o ambiente virtual `.venv`, instala o Django, gera o `.env` com uma chave secreta,
   cria o banco, carrega o conteúdo inicial e valida tudo. Use `setup.ps1 -RunTests` para rodar também os testes.
3. Dê dois cliques em **`Iniciar.bat`** (ou `run.ps1`). O servidor sobe e o navegador abre em
   `http://localhost:8000`.
4. Para encerrar, feche a janela do terminal (ou `Ctrl+C`).

Backup pelo terminal: **`Backup.bat`** ou `backup.ps1 -Label "antes-da-prova"`.

A instalação precisa de internet só para baixar o Django. Depois disso tudo funciona offline.
Docker não é necessário.

<details><summary>macOS / Linux</summary>

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_content
./run.sh
```
</details>

---

## O que tem na aplicação

| Área | O que faz |
|---|---|
| **Painel** | Capítulo atual, progresso geral, exercícios feitos, taxa de acertos, dias seguidos, tempo de estudo, revisões pendentes, competências fortes e frágeis, erros recorrentes e botão para continuar de onde parou. |
| **Capítulos** | Título, tema, objetivos, gramática, vocabulário, nº de exercícios, progresso, domínio estimado, avaliação e estado (não iniciado, em andamento, revisão necessária, apto para avaliação, concluído). |
| **Conteúdo do capítulo** | Explicações curtas, exemplos, tabelas de conjugação, observações, erros frequentes de falantes de português, vocabulário, expressões úteis, textos e resumo de revisão. |
| **Praticar** | Sessão com uma questão por vez; filtros por capítulo, tema, competência, dificuldade e quantidade; modo prática (correção imediata) ou avaliação (correção no fim); tradução de apoio; marcar para revisão; sinalizar problema; interromper e retomar; teclado de acentos franceses. |
| **Textos** | Leitura com o texto ao lado das perguntas; no fim, resultado, explicações, trecho que fundamenta cada resposta, vocabulário novo, estruturas úteis e “refazer só as erradas”. |
| **Revisões** | Fila de revisão espaçada (1, 3, 7, 14, 30 dias) priorizando erros e competências frágeis. |
| **Caderno de erros** | Questão, sua resposta, resposta correta, explicação, capítulo, competência, gramática, vocabulário, nº de erros, última tentativa, próxima revisão e estado (erro recente, em revisão, melhorando, superado). |
| **Produção escrita** | Textos guardados, resposta-modelo, critérios, autoavaliação ou correção manual posterior, marcação para revisar. |
| **Progresso** | Domínio por capítulo, competência (leitura, interpretação, escrita…), gramática, vocabulário e objetivo — com o cálculo explicado. |
| **Dados e backup** | Exportar conteúdo (tudo ou um capítulo), progresso, caderno de erros e exportação completa; importar pacotes JSON; criar, baixar e restaurar backups. |
| **Editorial / Administração** | Problemas sinalizados, relatório de validação do conteúdo, histórico de alterações e versões; cadastro completo pelo painel do Django. |
| **Créditos e fontes** | Fontes, autorias, licenças e origem de cada questão e texto. |

### Conteúdo inicial

| Capítulo | Questões | Textos | Avaliação final |
|---|---|---|---|
| 1. Bonjour et bienvenue ! | 96 | 3 | 10 questões |
| 2. Me voici ! | 104 | 4 | 10 questões |
| 3. Les vacances en France | 93 | 3 | 9 questões |
| 4. Les gens | 90 | 3 | 9 questões |

São **383 questões** cobrindo os **27 tipos de exercício** pedidos, todas as dificuldades de 1 a 5 em cada
capítulo, 13 textos de interpretação e 12 propostas de produção escrita. Os capítulos 0 e 5–13 do
*Français interactif* já estão no mapa curricular como “planejados”. O mapa completo está em
[`docs/CURRICULO.md`](docs/CURRICULO.md).

Todo o conteúdo é **original** (fonte “Cahier — conteúdo original”). Questões no formato da prova do DELF
são marcadas como **“inspiradas em formato de exame”**, nunca como oficiais.

---

### Atualizar o Cahier sem perder o progresso

Ao baixar uma versão nova (por exemplo, com `git pull`), rode `setup.ps1` de novo (ou
`.venv\Scripts\python manage.py seed_content`). O conteúdo inicial é carregado de forma **incremental**:
questões e textos novos são acrescentados; o que você já tem — inclusive edições feitas no painel —
fica como está, e seu progresso não é tocado. Por segurança, faça um backup antes (`Backup.bat`).

## Novidades

**v1.1** — 106 questões novas nos capítulos 1 a 4 e um texto novo por capítulo (mensagem da professora,
conversa no café do campus, previsão do tempo, retrato de uma amiga), além de frases úteis na sala de aula.
A importação ganhou o modo “manter os existentes e acrescentar só os novos”.

## Como funciona por dentro

- **Django 5.2 + SQLite + templates**, CSS próprio e JavaScript simples, sem CDN. A única dependência é o Django.
- Apps: `content` (currículo, textos, questões e versões), `learning` (sessões, correção, domínio, revisão,
  caderno de erros) e `portability` (importação, exportação, backup).
- Algoritmos de correção, domínio e revisão espaçada: [`docs/ALGORITMOS.md`](docs/ALGORITMOS.md).
- Formato JSON de importação/exportação: [`docs/FORMATO_JSON.md`](docs/FORMATO_JSON.md).

### Histórico preservado
- **Tentativas são imutáveis**: o modelo recusa qualquer alteração depois de gravado.
- Cada mudança no conteúdo avaliável de uma questão cria uma **nova versão** com um retrato completo
  (enunciado, alternativas, respostas, explicação). Cada tentativa guarda o número da versão respondida e
  o texto da resposta correta daquela versão — correções editoriais não reescrevem o seu histórico.
- Conteúdo não é apagado pelo painel: é **desativado** e continua no banco.
- A autoavaliação de um texto fica num registro separado (`WrittenAnswer`); a tentativa original não muda.

### Comandos úteis
```
.venv\Scripts\python manage.py seed_content            # acrescenta o conteúdo inicial que ainda falta (seguro repetir)
.venv\Scripts\python manage.py seed_content --update   # sobrescreve o conteúdo inicial com a versão dos arquivos
.venv\Scripts\python manage.py validate_content        # relatório de qualidade do conteúdo
.venv\Scripts\python manage.py import_content pacote.json [--dry-run] [--update | --skip-existing]
.venv\Scripts\python manage.py export_content saida.json [--kind conteudo|progresso|caderno|completo] [--chapter ch01]
.venv\Scripts\python manage.py backup_db --label nome
.venv\Scripts\python manage.py restore_db data\backups\arquivo.sqlite3 --confirm RESTAURAR
.venv\Scripts\python manage.py refresh_mastery         # recalcula o domínio
.venv\Scripts\python manage.py test tests              # testes automatizados
```

---

## Segurança e privacidade

- O servidor escuta **somente em 127.0.0.1**; `ALLOWED_HOSTS` aceita apenas `127.0.0.1`, `localhost` e `[::1]`.
- **Nenhum dado sai do computador**: sem telemetria, sem fontes ou scripts externos, sem APIs.
- Formulários com **proteção CSRF**; conteúdo exibido é escapado pelos templates do Django.
- Uploads validados: importação JSON até 5 MB (UTF-8, extensão `.json`, esquema verificado);
  restauração até 200 MB (cabeçalho SQLite, `integrity_check`, tabelas esperadas). Limites em `.env`.
- Restauração exige digitar **RESTAURAR** e sempre cria antes um backup de segurança.
- Backups usam a API de backup do SQLite (cópia consistente mesmo com o servidor aberto) e são verificados.
- **Sem senhas**: o painel administrativo usa um usuário local com senha inutilizável, logado
  automaticamente **apenas para acessos do próprio computador** (loopback). Acessos de outro endereço
  caem na tela de login.

---

## Decisões e suposições

Estas escolhas foram feitas sem consulta, por não serem bloqueantes; todas podem ser revistas.

1. **Conteúdo original em vez de adaptado.** O *Français interactif* está sob CC BY 4.0 e permitiria
   adaptação, mas ele serve aqui apenas como eixo curricular (sequência, temas, objetivos, gramática).
2. **Escopo inicial: capítulos 1 a 4**, o núcleo do A1. O capítulo 0 (alfabeto e fonética) é em boa parte
   oral; seus pontos escritos foram incorporados ao capítulo 1.
3. **Explicações e instruções em português; enunciados e textos em francês**, com tradução de apoio
   opcional (oculta no modo avaliação, e o uso fica registrado na tentativa).
4. **Avaliação final do capítulo**: questões reservadas (não aparecem na prática); 70% conclui o capítulo.
5. **Estados do capítulo**: “revisão necessária” quando há 3+ erros vencidos na fila ou acerto recente
   abaixo de 50%; “apto para avaliação” com domínio ≥ 60% e ao menos metade das questões respondidas.
6. **Acentos contam por padrão.** A tolerância a acentos é ligada por questão — no conteúdo inicial, só nas
   traduções para o português. Aceita-se `oe` no lugar de `œ` (limitação comum de teclado).
7. **Traduções e respostas abertas** usam listas de variantes ou expressões regulares; quando não há
   uma resposta fechada, a questão é de autoavaliação, com resposta-modelo.
8. **Questão nova acertada de primeira** entra na revisão com intervalo de 7 dias (manutenção); errada, com 1 dia.
9. **Servidor**: o `runserver` do Django, adequado para um único usuário local. Os estáticos são servidos
   pelo próprio Django, o que permite `DEBUG=false`.
10. **Fuso horário** padrão `America/Sao_Paulo` (para contar dias seguidos), ajustável no `.env`.
11. **Revisão pedagógica**: as questões foram verificadas na criação (francês, nível, clareza, resposta
    única, explicação) e há testes automáticos que garantem que cada uma é respondível com o próprio
    gabarito. Ainda assim, recomenda-se a revisão por um professor de FLE; use **Sinalizar problema**.

## Verificação feita

- **126 testes automatizados** aprovados: modelos, migrations, correção (exata, normalizada, acentos,
  regex, lacunas múltiplas), múltipla escolha, múltipla seleção, ordenação, pares, textos, domínio,
  revisão espaçada, caderno de erros, importação, exportação, backup e restauração, preservação do
  histórico, rotas, formulários, CSRF, escape de HTML, retomada de sessão e validação do conteúdo inicial.
- **Os 19 fluxos manuais** foram executados num navegador real (Chromium), com o servidor iniciado pelo
  `run.ps1`: abrir, iniciar capítulo, consultar conteúdo, iniciar sessão, acertar, errar, ver explicação,
  marcar, interromper e retomar, concluir, painel, caderno de erros, revisão, interpretação de texto,
  avaliação, exportação, importação, backup e restauração.
- `setup.ps1 -RunTests`, `run.ps1` e `backup.ps1` foram executados de ponta a ponta com PowerShell 7
  (em Linux, ajustando apenas o caminho do Python do ambiente virtual). Em Windows, os scripts são
  gravados em UTF-8 com BOM para funcionar também no Windows PowerShell 5.1.

## Limitações conhecidas

- Não há áudio, fala ou compreensão oral (fora do escopo, por decisão do projeto).
- Produção escrita não recebe nota automática: autoavaliação ou correção manual.
- Sem múltiplos usuários nem sincronização entre computadores (use exportação/backup).

## Evolução futura (publicar num servidor)

A estrutura já permite isso: defina `CAHIER_LOCAL_SINGLE_USER=false`, crie um superusuário
(`manage.py createsuperuser`), configure `CAHIER_ALLOWED_HOSTS`, use um servidor WSGI (gunicorn/waitress)
atrás de HTTPS e sirva `/static/` pelo servidor web (`manage.py collectstatic`). Para vários usuários,
seria preciso associar sessões, tentativas e revisões a cada conta.

## Solução de problemas

- **“a execução de scripts foi desabilitada”** → use os `.bat` ou `powershell -ExecutionPolicy Bypass -File setup.ps1`.
- **Porta 8000 ocupada** → `run.ps1 -Port 8001` (ou `CAHIER_PORT` no `.env`).
- **Python não encontrado** → reinstale o Python marcando “Add python.exe to PATH”.
- **Algo deu errado após uma importação** → *Dados e backup → Restaurar* com o backup mais recente.
