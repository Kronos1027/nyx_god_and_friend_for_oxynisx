# Aplicativos pela interface real da Nyx — 01/11/2026

## Caminho exercitado

Janela Qt de produção com dados temporários, Ollama/Qwen3.5:4b real, perfil
Normal, modo Assistida e voz desligada. O pedido entra pelo composer da própria
DesktopWindow, percorre OverlayWindow/TaskRunner/registry, abre PermissionDialog
e é autorizado por clique QTest no botão real. A guarda restringe o ensaio a
listagens e abertura do aplicativo escolhido; outras ações são recusadas.
Não há substituição de ferramenta/modelo por mock. A instância pessoal não é
operada e nenhum aplicativo pessoal é fechado. O corpo das respostas e títulos
de janelas permanecem somente nos traces locais ignorados, sem publicação.

O verificador externo em bench/native_windows.py usa EnumWindows/psutil,
sem importar catálogo, UIA ou ActionVerifier da Nyx. Confere janela visível e
nome de processo; ApplicationFrameHost exige também título exato do aplicativo.
Isso é verificação de abertura, não login, conteúdo ou funcionamento completo.

## Resultados

Primeira rodada por ferramenta standalone:

| Aplicativo | Execução1(s) | Execução2(s) | Execução3(s) |
|---|---:|---:|---:|
| Calculadora | 9,375 | 4,750 | 4,610 |
| Bloco de notas | 7,797 | 4,797 | 4,640 |
| Paint | 5,250 | 4,500 | 4,531 |

Todos9passaram. Calculadora não estava visível no primeiro pedido; nos seguintes
já estava aberta. Repetições não equivalem a partidas frias independentes.
O aquecimento do modelo é excluído; o primeiro driver não cronometrou esse
aquecimento. Drivers seguintes registram warmup_excluded_s.

Integração no runner M0, agora com correspondência exata de título UWP:

| Aplicativo | Execução1(s) | Execução2(s) | Execução3(s) |
|---|---:|---:|---:|
| Calculadora | 6,797 | 4,532 | 4,609 |
| Bloco de notas | 4,640 | 4,640 | 4,734 |
| Paint | 4,500 | 4,656 | 4,640 |

**9/9 verificadas**, nove confirmações autorizadas pelo botão, zero recusas,
zero divergências entre a abertura verificada pela Nyx e a observação Win32.
Cada execução registrou uma ação e workflow finished. O caso UWP da Calculadora
usou ApplicationFrameHost com título correspondente; não se aceitou só o host.
Teste negativo cobre outro app com nome Calculadora em um título de documento.

Antes da integração: categoriaApps tinha45linhas BLOCKED_HARNESS. Depois:
nove execuções reais e36bloqueadas, três dos15casos implementados. Taxa da
categoria no manifesto completo é20%, não100%. O gate continua falso por
cobertura incompleta e porque os aplicativos não são fechados/resetados entre
rodadas. O total do manifesto agora tem seis casos com rota segura e44pendentes.

## Qualidade e limites

- **929 aprovados,27 pulados,zero falhas em50,637s**, saída0; Ruff limpo
  incluindo bench/. Windows/browser reais habilitados, LPAC opt-in pulado.
  Fonte local: build/diagnostic/native-ui-final.xml.
- UI do harness renderizada fora da tela; as janelas dos aplicativos são reais,
  observadas pelo Windows. Não mede primeiro paint físico, DPI100/125/150% ou
  uso da aplicação após abrir. O clique QTest é só no diálogo da própria Nyx.
- RAM inclui harness/filhos e pode repetir memória compartilhada. VRAM é do
  sistema, não alocação exclusiva da Nyx; esses picos não validam o orçamento M7.
- Sem limpeza de apps pessoais. Artefatos existentes não são sobrescritos;
  retomada automática não repete operações R1 que ficaram em andamento.
- Não validados os12apps restantes, sessão logada de Spotify, distribuição
  congelada, hardware diferente, entrada em apps pessoais, voz ou bateria M1.
- Pet, assets, renderer, rotina e comportamento do overlay não foram editados.

Evidências: native_calculator_ui_2026-11-01.json,
native_notepad_paint_ui_2026-11-01.json e bench_native_apps_2026-11-01.json.
