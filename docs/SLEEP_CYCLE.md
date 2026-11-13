# Nyx — sono leve experimental (fase 1)

O objetivo é consolidar memórias *confirmadas* quando o computador estiver ocioso,
sem reservar um segundo modelo, sem rede, sem treinar pesos e sem executar ações.
A primeira implementação usa um índice de **revisão espaçada futura** (sleep_cards),
não sonhos conscientes. Nenhum card é tratado como um fato novo.

## No PC Windows, pelo código-fonte

Execute na raiz do projeto, usando o Python da .venv:

```powershell
.\.venv\Scripts\python.exe tools/nyx_sleep.py status
.\.venv\Scripts\python.exe tools/nyx_sleep.py enable
.\.venv\Scripts\python.exe tools/nyx_sleep.py once
.\.venv\Scripts\python.exe tools/nyx_sleep.py cards
.\.venv\Scripts\python.exe tools/nyx_sleep.py disable
```

- Por padrão, **desativado**; enable exige ação humana no terminal.
- once é uma manutenção manual. Feche a interface Nyx e não execute durante jogos.
- Exige RAM livre **>= 3 GiB**, telemetria disponível e orçamento de ociosidade.
- Lê até 24 notas explícitas da tabela facts (category='user_notes') por rodada.
- Notas com possíveis credenciais são ignoradas; a classificação é conservadora,
  **não substitui proteção criptográfica nem revisão humana**.
- Nunca lê automaticamente pesquisa externa, conversas integrais ou ferramentas como
  instruções. Não modifica a tabela original facts.
- Armazena no máximo 256 cartões e 50 auditorias, tudo no mesmo SQLite local.
- Se a nota for alterada/removida, o card associado é invalidado na próxima rodada.
- disable impede novas rodadas, sem apagar dados; delete_card remove card derivado.

## O que ainda não foi implementado

O algoritmo atual cria revisões de memória, **não realiza destilação nos pesos,
LoRA, fine-tuning, aprendizado por reforço ou geração de sonhos por LLM**.
Também não está acoplado a um temporizador do painel gráfico. As próximas etapas
são avaliação de recall com fatos controlados, monitoramento de regressões,
controle visual e agendamento ocioso com cancelamento e confirmação.

## Validação

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_sleep_cycle.py
.\.venv\Scripts\python.exe -m ruff check src/core/sleep_cycle.py tests/test_sleep_cycle.py tools/nyx_sleep.py
```
