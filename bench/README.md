# Bateria real da Nyx

`catalog.py` declara os 50 cenários enumerados no pacote, com pedido, categoria,
setup, verificador, prazo e risco. `tools/run_bench.py --list` mostra o inventário.
Somente leitura de oito arquivos e os dois casos de conversa possuem rotas
seguras completas neste primeiro incremento. Casos restantes são
`BLOCKED_HARNESS`, não passes e não prova de incapacidade da Nyx.

```powershell
.venv\Scripts\python.exe tools/run_bench.py --runs 3 --categories all --profile normal --output docs/evidence/bench_novo.json
pwsh -NoProfile -File tools/run_live.ps1 -Categories conversation -Profile normal
```

O script PowerShell roda Ruff, testes unitários, Windows live e o subconjunto da
bateria. `-m windows_live` ativa explicitamente as fixtures Windows/browser;
LPAC continua exigindo seu opt-in próprio. `-m 'not windows_live'` não ativa as
fixtures. A sessão interativa é sondada por Win32 sem ler conteúdo do clipboard.

Cada caso implementado usa Ollama/TaskRunner/registro reais, dados temporários e
guarda que impede ferramentas fora da fixture. Não opera a Nyx pessoal nem
aprova ações externas. O verificador em bench/verifiers.py não importa o
verificador da Nyx: lê arquivos e confere o texto entregue. O método pedido
(oito leituras/calculadora) também é conferido pelo ledger de produção, com essa
origem explícita; isso não é auditoria independente de syscalls de leitura.

Relatórios JSON e Markdown incluem cobertura, mediana das taxas de cada rodada,
variância, tempos, amostras de recursos e referência aos traces locais. VRAM é
uso total do sistema; RSS do harness/filhos pode repetir páginas compartilhadas.
Nenhum desses números representa pico exclusivo da UI da Nyx. Um gate só pode
passar com toda a cobertura selecionada executada e os limiares satisfeitos.
`milestone_complete` permanece false; o runner parcial não fecha M0–M8.

Resultados são gravados atomicamente, com até dez tentativas em recusa
transitória de compartilhamento do Windows. Se falhar, preserva o relatório
anterior e o temporário para diagnóstico. Um relatório existente só é retomado
com `--resume`, mesmo modelo/perfil/manifesto/rodadas e fingerprint de runtime e
verificador. Apenas rotas de leitura/conversa são retomadas automaticamente;
linhas concluídas não são repetidas. Traces brutos e temporários não vão ao Git.

O primeiro checkpoint legado não tinha fingerprint e sua retomada está marcada
como diagnóstica no próprio relatório. Há avaliação posterior da omissão de
calculadora em bench_2026-11-01_M0_partial_assessment.json; o PASS antigo nesse
caso representa somente números corretos e não o cumprimento integral do pedido.
