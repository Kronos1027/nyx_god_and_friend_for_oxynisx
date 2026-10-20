# Nyx — mascote

A mascote atual é a Oxynisx, reutilizada com autorização do usuário a partir do pet gerado no chat local. `assets/oxynisx/spritesheet.png` tem 1536×1872 pixels: oito colunas e nove linhas de células 192×208. Ciclos: idle (6), running-right (8), running-left (8), waving (4), jumping (5), failed (8), waiting (6), running (6), review (6). O arquivo original previa onze linhas, mas as duas linhas de direções do olhar ainda não estão na imagem entregue.

`SpriteRenderer` recorta os quadros e mantém cache limitado. O renderer procedural de coruja permanece apenas como fallback se o atlas estiver ausente ou inválido. Os efeitos de atividade são desenhados pela interface e não modificam a imagem original.

Os PNGs em `assets/sprites/` são versões exportadas anteriores. O overlay gera a imagem em runtime; para atualizar os PNGs versionados, use `SpriteRenderer.save_all_sprites()` no ambiente Windows com PyQt6.
