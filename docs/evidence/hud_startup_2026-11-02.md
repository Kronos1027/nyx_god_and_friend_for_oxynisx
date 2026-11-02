# M7 · Primeiro frame e painéis tardios · 02/11/2026

Estado: implementação e investigação de estabilidade; **não declarar eliminado o
pico nativo**. Última amostra3/3 ficou abaixo1,2s, mas rodada intermediária preserva
3,635s sem causa isolada. Não atribuir isso ao ambiente sem evidência específica.

## Mudança

`src/ui/desktop.py`: Agenda e Central são criadas na primeira visita. Configurações
e Aprendizado mantêm os controles de política/permissões inicializados, mas suas
árvores só entram no layout/estilo da janela quando visitadas. Índices das páginas
preservados; atividades anteriores à primeira Central são armazenadas em buffer
limitado e apresentadas ao abrir. Estado de parada é consultado no momento em que
a Central é criada. Ao fechar, páginas ainda não anexadas também são liberadas.

Não importar o Estúdio inteiro apenas para aplicar tema: atualizar somente uma
instância que já exista. A última rodada confirma `studio_imported=false` no
primeiro frame, quatro painéis diferidos e dois ainda não construídos. Pet,
sprites, rotina, overlay, permissões e comportamento dos backups preservados.
Nenhuma dependência nova.

## Método e resultados

`tools/measure_hud_startup.py` executa três processos Python novos com dados
sintéticos no volume do projeto. Mede imports, QApplication, controller,
construtor, show e primeiro evento Paint observado. Também registra a conclusão
do primeiro lote de eventos. Não é prova de pixels no monitor nem medição do
launch completo de `main.run_gui`, que ainda prepara registro/modelo/memória antes
de construir a janela. Voz e modelo não são carregados. O timestamp de processo
começa no início do script; não inclui o lançamento do interpretador pelo Windows.

| Rodada | Primeiro Paint desde início do script | Desde QApplication | RSS |
|---|---|---|---|
| Antes |1,594 /0,944 /0,947s|1,102 /0,703 /0,700s|166,88 /166,15 /166,10MiB|
| Anexação tardia inicial |0,945 /0,909 /0,914s|0,705 /0,661 /0,672s|161,53 /161,66 /161,46MiB|
| Fábricas Agenda/Central |0,943 /**3,635** /1,101s|0,710 /**3,401** /0,852s|160,78 /161,15 /160,90MiB|
| Rechecagem final com cProfile |0,987 /0,923 /0,901s|0,719 /0,688 /0,665s|163,79 /163,48 /163,49MiB|

Fontes: [antes](hud_startup_before_2026-11-02.json),
[primeiro ajuste](hud_startup_after_2026-11-02.json),
[fábricas e pico preservado](hud_startup_final_2026-11-02.json),
[perfil final](hud_startup_profiled_2026-11-02.json).

Não chamar isso de ganho comprovado3,5→0,9s: o3,541s anterior é histórico e não
se repetiu na nova baseline; cache de arquivos/fontes não foi esvaziado. Medianas
observadas desde o script0,947→0,923s; a diferença pequena sofre variação do PC e
a rodada final tem overhead do profiler. RSS sem profiler166,15→160,90MiB de
mediana. CPU ociosa10s nas fábricas:0,469/0,468/0,781%, dentro1%; amostras1–2s
variaram acima da meta e não foram usadas para afirmar CPU ociosa estável.

O pico3,635s ocorreu no construtor:3,225s, enquanto builders/preferências
instrumentados somaram aproximadamente0,45s. O perfil posterior não reproduziu
o pico: `winId`0,134–0,144s, SpriteRenderer congelado~0,089s, stat/leitura de código
~0,075s e SQLite executescript0,020–0,035s. RAM livre nessa rodada~3,1GiB; isso
não prova a causa da rodada lenta anterior, que ainda precisa de trace de I/O/
espera durante o pico. Não afrouxar a meta ou apagar essa evidência.

## Verificação e próxima ação

- Antes da mudança:48testes desktop verdes. Depois:49/49, incluindo primeira
  navegação tardia e regressão de parada/privacidade/confirmar/streaming.
- Ruff de src/tests/tools limpo; gate completo fica para integração root, sem
  disputa de recursos com a prioridade M3.
- `check_ui.py`:9/9interações em100/125/150%,0achados horizontais, contraste
  aprovado.90PNGs (28telas+2paletas por escala) revisados em folhas de contato;
  nenhum novo problema visual encontrado. Capturas em build/previews, fora Git.
  Dados: [QA](hud_startup_ui_2026-11-02.json).
- Não validados: causa do pico, arranque completo com modelo/memória, verdade
  factual, OBS/monitor físico, navegação completa por Tab e todas as rolagens.
- Próximo: capturar a chamada bloqueada numa ocorrência lenta nativa e separar
  backend/UI no arranque real; não mexer no pet para ganhar tempo.
