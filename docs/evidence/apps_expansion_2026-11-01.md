# Expansão Apps — diagnóstico parcial, sem aceite do marco

Rotas do harness ampliadas de3para12apps nativos. Os50casos do manifesto e
três repetições permanecem; Chrome, Spotify e WhatsApp ainda sem rota segura.
Chrome e os dois serviços nativos não foram encontrados no catálogo deste PC.
VS Code ausente; Antigravity disponível como alternativa explicitamente pedida.

Correções:

- Explorador exige CabinetWClass/ExploreWClass, além do executável: área de
  trabalho Progman/WorkerW não comprova uma janela de arquivos. Baseline real
  encontrou três falsos sucessos; artefato mantido, verificador não afrouxado.
- Terminal prefere AUMID registrado de Windows Terminal ao forwarder wt.exe.
- Pedidos simples e inequívocos de abrir apps conhecidos replanejam navegação
  ou shell não solicitados; leitura de processos não equivale a abrir Terminal.
  Não altera pedidos compostos de navegação/pesquisa. Regra deliberadamente
  restrita, sem pretensão de compreender universalmente qualquer frase.
- Handoff de splash/launcher só é aceito se nova observação identificar uma
  janela do mesmo app em foreground. A conferência no fim da tarefa permanece.
- Auxiliar anuncia PID real; cliente valida parentesco e criação antes de
  delegar foco. Popen podia apontar para intermediário do venv. Encerramento
  agora alcança apenas processos próprios com identidade validada, inclusive
  intérprete descendente. Não encerra apps pessoais.
- Foco usa sincronização temporária das threads, com detach garantido; falha
  em liberar encerra somente o auxiliar. Watchdog/árvore de processos limitam
  bloqueio nativo. Sem elevar privilégios, ASFW_ANY ou alteração de configuração.
- Harness admite janela temporária visível e suspende novas tarefas ao detectar
  falso sucesso ou pressão de memória. Permissões de produção mantidas.

Evidências reais, todos os nomes abaixo recebem sufixo `_2026-11-01.json`:

| Relatório | Resultado observado |
|---|---|
| native_apps_expanded_light |4/15; três falsos sucessos do Explorador|
| native_explorer_terminal_fixed |7/9; Terminal ainda com escolha de shell|
| native_apps_routing_fixed |12/12: Edge, Explorador, Configurações, Terminal|
| native_apps_expanded_heavy |1/12; RAM caiu para0,77–0,81GiB e bloqueou inferências|
| native_apps_handoff_fixed |3/12; foco e rota do Discord ainda falharam|
| native_apps_visible |3/15, todos os três passes do Discord|
| native_worker_identity_fixed |3/15, sem divergências falsas; foco ainda falhou|
| bench_apps_expanded |7execuções,2passes,29BLOCKED_RUNTIME,9BLOCKED_HARNESS|

O último runner integrado foi interrompido corretamente por pressão de RAM na
sétima tarefa. Não representa3rodadas completas: as tentativas restantes ficam
no denominador. Mediana de aprovação0%, categoria não aprovada, saída1.
Janelas visíveis/aberturas parciais não foram promovidas a conclusão.

Foco: UIA apresentou erro COM-2146233079; APIs nativas apresentaram acesso
negado ou ativação não concedida. A sincronização passou12/12nos casos próprios
de desktop depois de oito falhas numa execução intermediária. Esses resultados
não estabelecem a causa dos bloqueios nos apps instalados. Consultas R0 mostraram
integridade média8192, sem elevação/UIAccess, job sem restrição de UI reportada;
não justificam contornar proteções. Registrar bloqueio e seguir outras lacunas.

Regressão final no Windows: **970aprovados,27pulados,0falhas**,997casos,
49,845s; Ruff limpo incluindo bench. Não-live separado946passes/1skip,37,268s.
XMLs/logs privados em build/diagnostic; não publicados com host/caminhos locais.
Auxiliar real:3/3inicializações/encerramentos, zero processos restantes;
startup0,281–0,312s, RSS da árvore24,32–24,33MiB em snapshot, não pico.
Detalhes em `worker_lifecycle_2026-11-01.json`.

Não validado: gate Apps≥95%, reset de apps, execução manual com clique físico,
Chrome, login/mídia Spotify/WhatsApp, distribuição congelada ou soak2h. Nyx pessoal
não foi operada/reiniciada; pet e comportamento do overlay não foram modificados.

Fontes técnicas: [AllowSetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-allowsetforegroundwindow),
[AttachThreadInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-attachthreadinput).
