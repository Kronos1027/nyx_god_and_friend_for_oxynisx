# M3 — ações por referência e sessão visível persistente

## Entrega e evidência

`BrowserSession()` agora inicia visível e usa exclusivamente um perfil próprio
marcado da Nyx. No modo fonte, o perfil fica no volume do projeto, em
`data/browser_profiles/default`; instalado, no diretório de dados da Nyx.
`persistent_profile=None` continua sendo a escolha explícita para sessão
temporária; os diagnósticos e fixtures usam essa opção e modo headless.
Diretório pessoal preexistente sem identificação Nyx continua recusado.

Além de click/type, refs de `inspect` aceitam select, hover e press. Select só
aceita SELECT simples e opção única/habilitada, usa teclas CDP e confere o valor.
Hover confere o estado `:hover`. Press e type com submit só confirmam efeito
quando `expected_text` é observado; envio isolado não vira conclusão verificada.
Select, press e submit exigem confirmação por código, inclusive em modo autônomo.
Senha, referência antiga, alvos misturados e tecla fora da lista são recusados.
Trocar/criar/fechar aba invalida o snapshot. Hit-testing em iframe same-origin
agora confere também cobertura por Shadow DOM; transformações de escala são
recusadas quando a projeção de coordenadas não pode ser confirmada.

Na fixture HTTP própria, select/hover/press/type-submit passaram3/3 no Edge real,
com valores e eventos `isTrusted` conferidos diretamente no documento. Não usa
cookies pessoais nem autenticação. A observação independente confere o estado
da fixture; não é a bateria de pedidos pelo modelo ou pela UI da Nyx.
Tempos do caso completo, incluindo navegação e inspeção:0,794/0,795/0,616s.

Sessão visível padrão foi iniciada e encerrada duas vezes com perfil próprio:
armazenamento sintético persistiu em2/2; startup0,719/0,610s. Evidência:
[m3_visible_profile_2026-11-02.json](m3_visible_profile_2026-11-02.json).
São duas sondagens diagnósticas, não três execuções do gate.

## Regressão e métricas

- Ruff em src/tests/tools: limpo.
- Browser/verifier:64aprovados,0falhas,0skips,15,32s;26casos de navegador real
  (15 AX/Shadow/frames/novas ações e11regressões browser).
- XML privado reproduzível em build/diagnostic/m3-second-tests.xml, fora do Git.
- Antes: select/hover/press não eram expostos; padrão era headless temporário.
  Depois: três ações reais repetidas3× e padrão visível persistente medido2×.
  Não há latência baseline dessas ações, portanto não se afirma ganho percentual.
- Nenhuma dependência nova. RAM/VRAM não foram medidas novamente neste incremento;
  o valor anterior em m3_shadow_metrics_2026-11-02.json não é redução de recursos
  nem medição exclusiva desta entrega.

Comando da regressão:
`NYX_TEST_BROWSER=1 python -m pytest tests/test_browser_tool.py tests/test_browser_accessibility.py tests/test_browser_accessibility_live.py tests/test_browser_live.py tests/test_browser_profile.py tests/test_browser_scopes.py tests/test_browser_transport_lifecycle.py tests/test_verifier.py -o addopts='' -q`

## Limites e próximo passo

M3 permanece parcial: faltam gate integrado de tarefas pelo modelo/UI, benchmark
CDP versus Playwright, OOPIF cross-origin, upload/download, diálogos JS e pesquisa
com fontes. Persistência sintética não prova login pessoal. Não foi executada
ação em navegador pessoal. O HUD mantém a preferência existente do usuário;
a integração do padrão de UI pertence à entrega M7. Próximo: integrar HUD e
navegador, exercitar confirmação de produção e ampliar a bateria sem transformar
bloqueio de ambiente em aprovação.
