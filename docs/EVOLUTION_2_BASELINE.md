# Evolution 2.0 — baseline de 22/10/2026

## Origem e preservação

O HEAD remoto de `Kronos1027/nyx_god_and_friend_for_oxynisx/main` foi
consultado e obtido: `f1fb9a5d75e10e36d0248198e653164506e49da3`.
Todos os arquivos de código/documentação presentes nesse commit coincidem
com a pasta local, desconsiderando CRLF. Não há mudanças posteriores no remoto.

A pasta estava em `main` do repositório antigo (`5244876`), com arquivos
modificados e não rastreados. A nova branch `codex/nyx-evolution-2` foi alinhada
ao remoto correto por atualização apenas do índice/HEAD, preservando os arquivos.
A `main` local ficou intacta. Nenhum push, merge, instalação ou release foi feito.
Dados pessoais não foram adicionados ao Git. Arquivos locais adicionais continuam
fora dos commits da evolução.

Cópia local anterior: `build/evolution-baseline/source-before.zip`, patch e
inventário Git na mesma pasta (ignorados pelo Git). Preserve esses artefatos.

## Medições antes das alterações

- Python 3.11.15, Windows build 26300, PyQt6 6.11.0.
- `python -m pytest`: **435 passed, 1 skipped**, 23,50 s; aviso COM pywinauto.
- `python -m ruff check src tests`: aprovado.
- RAM física: 16.307 MiB; disponível na amostra: 2.402 MiB.
- CPU na amostra de 1 segundo: 26%.
- RTX 3060: 12.288 MiB totais, 1.372 MiB usados, 10.744 MiB livres.
- Ollama inicialmente desligado: conexão local recusada (WinError 10061).
- Playwright e SDK MCP não instalados; sem Docker ou WindowsSandbox no PATH.
- Esses números são amostras do sistema, não consumo atribuído à interface Nyx.
- Evidências brutas: `build/evolution-baseline/{pytest.txt,pytest.xml,resources.json,comparison.json}`.

## Inventário e riscos encontrados

Existem interface PyQt/Oxynisx, voz Kokoro/faster-whisper, agente com ferramentas
e confirmações, tarefas limitadas, memória SQLite, navegador CDP isolado,
pesquisa de documentação, backup e laboratório declarativo. Os testes existentes
misturam unidades com integrações temporárias; aprovação da suíte não comprova
Spotify, microfone ou qualidade do modelo em tarefas gerais.

Falhas prioritárias observadas por leitura de código:

1. `code_task` executa pytest mesmo em proposta e é registrado como insensível
   quando `apply=False`; o papel patch pode chegar a essa execução.
2. CodeAct chama subprocesso com ambiente do usuário e descreve CWD como sandbox.
   `task_name` e `filename` permitem caminhos fora do workspace.
3. CodeTask retorna de algumas exceções sem restaurar edições já realizadas.
4. Timeouts da equipe aguardam o encerramento do executor, e informam interrupção
   sem realmente cancelar a operação em andamento.
5. Inferência FIFO sem prioridade/cancelamento de espera; telemetria GPU lança
   processo a cada consulta. Recursos disponíveis são escassos nesta máquina.
6. Iniciativa é convite fixo por tempo; tarefas não possuem checkpoint persistente.
7. MCP tem allowlist vazia permissiva e leitura bloqueante; skills não estão
   integradas ao runtime. Essas áreas precisam de evolução antes de uso ampliado.

## Execução da missão

Fases A–J seguem a ordem do prompt. Cada etapa terá código, testes e commit
próprios. Resultados reais, testes roteirizados e impedimentos externos serão
registrados separadamente. Nenhuma capacidade será declarada concluída só por
existir uma classe ou um botão. O objetivo completo permanece em andamento.
