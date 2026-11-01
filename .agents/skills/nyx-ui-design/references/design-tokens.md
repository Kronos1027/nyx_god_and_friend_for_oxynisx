# Tokens e regras visuais

**Contrastes medidos (WCAG)** em Midnight: texto sobre ink 16,6 · sobre surface2 13,8 · muted ≥ 5,7 · dourado ≥ 9,1 · turquesa ≥ 8,7 · vermelho ≥ 5,4. `dim` (#6573A8) só para decoração/linhas, nunca texto. Daylight: texto 16,7+ · muted 6,5 · dourado/turquesa/vermelho ≥ 4,8. Rode `tools/check_ui.py` para reconferir qualquer mudança de token.

**Semântica de cor (não misture)**
- Dourado: foco, tarefa ativa, botão primário, anel de foco do teclado (2 px).
- Turquesa: percepção/presença, sucesso verificado, microfone ouvindo.
- Vermelho: parar, destrutivo, R3, erro. Sempre com ícone + rótulo (nunca só cor).
- Neutros azul-marinho para estrutura. **Sem violeta/lavanda.**

**Tipografia**: UI em Inter 14; rótulos/dados em JetBrains Mono 11–12 maiúsculas com tracking +6% (estilo HUD). Títulos 16/22 peso 600. Evite negrito em corpo de texto.

**Forma**: grade de 4 pt; cartões 8 px, painéis 12 px, chips pílula; bordas 1 px `line`; sem sombras pesadas (elevação por superfície e borda); brilho só em estado ativo (anel/linha dourada ou turquesa, ≤ 1 Hz).

**Movimento**: 120–220 ms OutCubic; nada em loop além do pulso de atividade; respeitar "reduzir movimento" e parar timers com a janela oculta.

**Anel do pet** (apenas o anel, não o sprite): dourado = pensando/executando, turquesa = ouvindo/percebendo, vermelho = erro/parada, apagado = ocioso.
