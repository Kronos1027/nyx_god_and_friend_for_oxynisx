# Especificação de layout e comportamento — Nyx HUD

Princípio: **conversa primeiro, prova de percepção sempre à vista, zero ruído**. Minimalista, futurista, teclado-primeiro (estética de WM em tiling, tipo Hyprland): linhas finas, translucidez sutil, dados em mono, nada decorativo que custe CPU/GPU.

## Estrutura (padrão 1180×760, mínimo 960×640)
```
┌ status strip (36) ───────────────────────────────────────────────────────┐
│ MODELO qwen… 82 tok/s · VRAM ▮▮▮▯▯ 6.9/12 · PERFIL NORMAL · PERMISSÃO PARCEIRA · PRESENÇA ● │ [■ PARAR] │
├ rail │ conversa (centro)                                   │ AGORA (300, Ctrl+.) ┤
│ 56   │  mensagens + cartões de ação/confirmação inline     │ janela ativa         │
│      │                                                     │ tocando              │
│      │                                                     │ jogo                 │
│      │  ┌ compositor: / comandos · @ apps/arquivos · mic ┐ │ tarefa atual (passos)│
│      │  └────────────────────────────────────────────────┘ │ recursos             │
└──────┴──────────────────────────────────────────────────────┴──────────────────────┘
```
- **Rail (56 px, ícones; expande a 200 px ao fixar)**: Conversa (padrão), Tarefas, Agora, Memória, Apps & Skills, Configurações; rodapé: indicador de perfil + botão Modo Privado.
- **Status strip**: cada item é clicável e abre seu seletor (modelo, perfil, permissão, presença). **PARAR** sempre visível (vermelho, contorno), atalho `Esc Esc` global.
- **Conversa**: mensagens do usuário à direita discretas; Nyx em blocos de largura total, sem balão, com linha lateral de 2 px (dourada enquanto pensa/executa, turquesa quando concluiu verificado). Streaming com cursor. Mensagens longas colapsam.
- **Cartões de ação inline**: `ABRIR APP · Spotify ✓ janela confirmada · 1,4 s` com traço expansível (ação, parâmetros, verificador, tempo, erro tipado). Falha mostra causa + próxima sugestão + botão "tentar outro jeito".
- **Cartões de confirmação inline (não modais)**: mostram o texto/efeito exato e a classe de risco (R1/R2/R3), botões `Aprovar` `Editar` `Negar`, "sempre permitir para <app/domínio>" só em R1. Para plano multi-etapas: lista numerada com **Aprovar plano**.
- **Cartões de pesquisa**: resposta + chips de fontes (título, domínio, data); clique abre.
- **Painel AGORA**: janela ativa (ícone + título), mídia tocando (título/artista), jogo, tarefa atual como stepper (✓ verificado · … em andamento · ✕ erro com causa) com cronômetro e botão cancelar, mini-medidores VRAM/RAM/CPU. Miniatura de tela **desligada por padrão**. Selo **MODO LIVE** quando ativo. Aqui também fica o pet no anel de estado (sprite inalterado).
- **Paleta de comandos `Ctrl+K`**: busca fuzzy em ações, apps instalados, conversas, memórias, skills, configurações; mostra atalho de cada item.
- **Mini-HUD (cápsula 320×56 perto do pet)**: ponto de estado, legenda ao vivo (o que faz/diz), botão parar. Atalho global `Ctrl+Alt+N` mostra/oculta a janela principal. Opção "Ocultar da transmissão" (`SetWindowDisplayAffinity` com `WDA_EXCLUDEFROMCAPTURE`) **ligada por padrão** para a janela principal; o pet continua capturável pelo OBS.
- **Onboarding (primeira execução, ≤ 60 s, 4 passos)**: (1) checagem de hardware e escolha automática do modelo; (2) consentimento de Presença por sensor; (3) modo de permissão (Assistida / Parceira) com exemplos; (4) teste de voz e wake word. Pular = padrões seguros.
- **Configurações** (busca no topo; 5 grupos): Geral (tema, idioma, atalhos), Modelo & Recursos (perfis, modelo fixo), Permissões & Privacidade (allowlists, sensores, linha do tempo, apagar tudo), Voz, Avançado (diagnóstico, logs, backups). Sem formulário gigante: cada opção com uma linha de explicação.
- **Estados**: vazio (uma ação clara), carregando (esqueleto, nunca spinner infinito), erro (causa + botão). Nenhum cartão "indisponível" sem ação.
- **Temas**: Midnight (padrão) e Daylight; acento escolhível entre dourado/turquesa. Remover os demais temas.

## Atalhos
`Ctrl+K` paleta · `Ctrl+L` compositor · `Ctrl+.` painel Agora · `Ctrl+Shift+P` Modo Privado · `Ctrl+Shift+L` Modo Live · `Esc Esc` parar tudo · `Ctrl+/` ajuda de atalhos · `Ctrl+Alt+N` global.

## Orçamentos
UI ocioso ≤ 180 MiB RAM, < 1% CPU; primeiro paint < 1,2 s; redimensionar sem travar; nenhum timer rodando com janela oculta.
