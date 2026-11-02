# Sensores reais no AGORA · 02/11/2026

**Marco:** incremento de percepção do HUD implementado e verificado nas fixtures
abaixo. Isso não conclui Presença/memória/voz nem o arranque completo da Nyx.

**O que mudou:** `src/core/presence_sensors.py`, `windows_media.py`,
`context_awareness.py`, `src/ui/desktop.py`, `src/ui/hud/agora_panel.py` e
`status_strip.py`. O painel recebe janela ativa, nomes de processos, mídia
publicada no Windows e candidatos de jogos conhecidos. Cada novo sensor exige
opt-in separado e começa desligado. A autorização antiga de observar encerramento
de PIDs escolhidos não autoriza inventariar todos os nomes.

Janela ativa usa WinEventHook de foreground/mudança de título, com consulta
inicial e fallback de polling se a assinatura for negada. O callback não lê texto.
Mídia usa GSMTC por Windows PowerShell 5/WinRT já instalado, sem pacote novo.
Nenhum argumento, caminho de processo, imagem, cookie ou conteúdo de página é lido.
Títulos/metadados são efêmeros; não entram no banco de eventos, chat ou logs.
Observação só acontece enquanto a janela e AGORA estão visíveis. Sem opt-ins,
não é criado worker. A consulta dos demais campos pode levar cerca de6s; mídia
tem cache de até12s. Dado antigo é marcado após20s, sem afirmar contexto atual.

Modo Privado remove hooks, cancela o helper próprio, limpa valores/cache e
invalida resultados pendentes sem apagar consentimentos ou histórico. Revogar e
autorizar novamente também invalida leitura anterior. Revisão externa encontrou
e corrigiu duas corridas: cache de janela reposto depois de stop e helper criado
logo após pausa. Há regressões com sincronização por eventos para ambas.

Jogo/Live não inicia o helper de mídia nem varre inventário. A consulta leve
lê somente nome do app/PID em primeiro plano, sem título; jogo é classificado
por lista limitada de nomes. No Normal, reconhecer processo não prova partida
ativa, razão pela qual o HUD informa “Processo detectado”.

Navegadores conhecidos mostram somente nome do app, sem consultar o título.
GSMTC não informa se a origem é uma aba anônima; propriedades só são lidas de
players desktop reconhecidos. Origem desconhecida/navegador mostra apenas estado,
com metadados ocultos. Outros filtros de janela são heurísticos, não uma garantia
universal para qualquer app; Modo Privado continua sendo a pausa abrangente.

**Evidência:** [três processos nativos novos](presence_sensors_2026-11-02.json),
[ensaio inicial preservado](presence_sensors_initial_2026-11-02.json),
[QA offscreen](presence_sensors_qa_2026-11-02.json),
[custo do helper](presence_helper_cost_2026-11-02.json).

`tools/verify_presence.py --runs 3 --output <relatório>` exercita o DesktopWindow
de produção com estado temporário, controles reais de consentimento e observação
Win32 independente da própria janela. A fixture de mídia é um MediaPlayer real,
WAV local silencioso/volume zero, MediaPlaybackItem com título único e estado
publicado no Windows. Um executável C# próprio chamado cs2.exe comprova somente
classificação por nome; PID/criação são conferidos antes do cleanup. Nenhum
programa pessoal foi encerrado. O relatório público guarda booleans/métricas,
sem nomes coletados, títulos pessoais, PIDs ou capturas.

**Métricas antes→depois:** antes, campos sem sensores conectados. Depois,
57/57 verificações funcionais/privacidade, três execuções. O ensaio inicial
teve42/42, mas reutilizava QApplication sem destruir widgets: RSS141,898→190,055
→236,836MiB, com timer de lembrete de fixture antiga. Esse erro de harness foi
preservado; a versão atual usa processos novos e destruição explícita de Qt.

| Execução nativa nova | RSS UI | CPU UI ociosa (10s) |
|---|---:|---:|
|1|142,480MiB|0,625%|
|2|142,383MiB|0,469%|
|3|142,055MiB|0,625%|

Mediana RSS142,383MiB; valores desta amostra atendem180MiB/<1% para o processo
da UI. Não são o consumo agregado de toda Nyx nem o launch completo com modelo,
memória e catálogo. O helper temporário de mídia mede89,855–90,652MiB pico,
0,345–1,316s de duração e0,422–0,828s de CPU por início. Ele é consultado no
máximo a cada12s e fica desligado em Jogo/Live. Sem instalação/download; novos
módulos de runtime somam aproximadamente21KiB. VRAM não foi medida neste probe;
não há inferência/GPU no caminho implementado.

**Testes:** Ruff de src/tests/tools limpo. Gate completo da worktree:
1000passes/65skips/0falhas,1065casos,44,662s. Os78testes focados anteriores
passaram; a última proteção de títulos de navegadores recebeu rechecagem focada.
`check_ui.py`:27/27 interações nas escalas100/125/150%, contraste aprovado e
0achados horizontais.90PNGs dos dois temas revisados em15folhas de contato:
novos controles cabem e o painel mantém rolagem; sem nova sobreposição.
`preview_desktop.py` também executado. Capturas permanecem fora do Git.
QA offscreen inicial registrou CPU1,562/1,093/0,781% e primeiro frame
0,645/0,479/3,142s; esses números anteriores à otimização “sem opt-in/sem worker”
não foram apagados nem usados como prova de desempenho nativo estável.

**O que NÃO foi validado:** percepção com HUD oculto (ela pausa), partida real
de cada jogo, mídia de toda aplicação, som nos alto-falantes, detecção universal
de janelas privadas, OBS real, uso prolongado/soak, voz ou conversa contextual.
Existe API curta `context_snippet()` com expiração/consentimento, mas não está
ligada ao LLM: fazê-lo exige evitar eco em chat/log e esclarecer armazenamento.
Não se habilitou nenhum sensor na instância ou nas preferências pessoais.

**Riscos:** assinatura de hooks pode ser negada e usar polling; lista de jogos e
identidade por nome são limitadas; PowerShell acrescenta custo transitório quando
mídia é autorizada. A proteção conservadora oculta títulos de navegadores e mídia
de origens não reconhecidas. Não confundir ausência de observação com ausência
de app/jogo no PC.

**Próximo marco:** integrar em nyx-2, preservar os opt-ins e conectar contexto
à conversa somente após tratar retenção. Gate completo de Presença/memória/voz
continua pendente; prioridade M3 permanece com o agente principal.

Referências primárias: [GSMTC RequestAsync](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager.requestasync),
[metadados](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession.trygetmediapropertiesasync),
[identidade da fonte](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession.sourceappusermodelid),
[MediaPlaybackItem/SMTC](https://learn.microsoft.com/en-us/windows/apps/develop/media-playback/integrate-with-systemmediatransportcontrols).
