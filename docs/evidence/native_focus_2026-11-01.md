# Abertura nativa, foco e conferência final — incremento parcial M0/M1

O ensaio integrado anterior passava9/9pela janela, mas apenas3/9estavam em
primeiro plano no encerramento. O artefato original continua preservado:
`bench_native_apps_2026-11-01.json`. Sua aprovação era de janela, não de foco.

Correções em ui_tool/installed_apps/app_catalog/task_runner:

- Spotify/WhatsApp procuram instalação nativa primeiro; somente NOT_FOUND
  permite alternativa web, informada no resultado. AMBIGUOUS não dispara web.
  Alias zap acrescentado. Nenhum desses dois apps foi encontrado neste catálogo;
  preferência nativa coberta por regressão unitária, ainda sem instalação real.
- Janela já aberta é focalizada sem relançar. Sem foco confirmado, resultado
  UNVERIFIED, sem registrar sucesso. Janela que mudou fica ELEMENT_STALE.
- DWM exclui superfícies UWP cloaked, embora tenham WS_VISIBLE. Calculadora
  apresentou cloaked=2 numa CoreWindow sem relação ativa com o frame visível.
- Quando a última ação é abertura nativa, o encerramento reconsulta o aplicativo
  e foreground após a resposta do modelo, sem nova abertura/foco. Falha substitui
  a confirmação por aviso honesto, preserva erro e marca etapa não verificada.
- Verificador independente também exige DWM sem cloak; host UWP exige título
  exato e processo filho do app. Não importa o código de verificação da Nyx.

Resultados reais, interface de produção isolada, QTest no diálogo real,
Qwen4/Normal, Calculadora/Bloco de notas/Paint3×cada:

| Ensaio | Janela+foco finais | Divergência após confirmação |
|---|---:|---:|
| native_focus_ui |6/9|0 (Calculadora falhou honestamente)|
| native_focus_dwm_ui |8/9|1 (foco mudou antes do fim)|
| native_focus_final_ui |9/9|0|
| bench_native_focus_normal |9/9|0|

Todos os JSONs são de01/11/2026 e mantidos nesta pasta. O falso sucesso
intermediário não foi apagado; motivou a conferência final. Dois ensaios posteriores
passaram nas três repetições, sem promover a categoria completa.

Mediana integrada4,640→4,781s; RAM máxima do harness/descendentes272,82→276,07MiB;
GPU total do sistema5173,88→5312,76MiB. Amostragem250ms, RSS pode duplicar páginas
compartilhadas, GPU não exclusiva da Nyx. Não são condições de carga controladas
nem comprovação de UI≤180MiB. Modelo aquecido separadamente; pet preservado.

Uma tentativa integrada com perfil Conservador bloqueou antes da inferência por
RAM livre1,54GiB/orçamento de pesos1,63GiB versus modelo3,10GiB. Relatório
`bench_native_focus_final_2026-11-01.json` preservado. Repetição Normal explícita,
igual aos ensaios anteriores, passou; nenhuma proteção reduzida ou app fechado.
Falhas iniciais do runtime agora conservam o erro tipado no relatório do pai.

Cobertura Apps continua9/45tentativas,36BLOCKED_HARNESS,20% no manifesto,
gate inelegível por cobertura e ausência de reset. Saída1 do runner é esperada
e não foi convertida em sucesso. Sem login, mídia, aplicativos pessoais encerrados,
reinício da Nyx pessoal, distribuição congelada ou push.

Regressão final:949aprovados,27pulados,zero falhas,48,178s (976casos),
Ruff limpo incluindo bench. XML/log privado em `build/diagnostic/app-final-gate.*`.
As seis falhas de foco da execução anterior não reapareceram nesta suíte;
esse resultado não prova ausência de interferência de foco no uso cotidiano.
Dois fingerprints SHA-256 desses relatórios foram auditados como código, sem
ignorar arquivos/plugins no scanner. Nenhum valor de credencial foi utilizado.

Fonte técnica: [atributos DWM da Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute).
