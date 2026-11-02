# Abertura, foco e denominador instalado — 02/11/2026

Marco M1 **parcial: bloqueado por ambiente**, conforme direção do usuário.

Antes: janela confirmada sem foreground era tratada como falha de abertura;
o catálogo fixo também incluía apps ausentes. Depois: a ferramenta e a guarda
final confirmam janela visível/identificada separadamente de `focus_verified`.
Se o Windows negar foco, a saída informa “Abri…, mas não consegui trazer pra
frente”. O bench exige ainda janela nova e `opened=true`; janela pré-existente
não vale como abertura fria. Filtro DWM/identidade independente preservado.

Pré-checagem R0 real: [JSON](app_precheck_2026-11-02.json). Catálogo 15 →
denominador instalado 12. Chrome, Spotify e WhatsApp excluídos por inventário
Menu Iniciar/App Paths/binários/janelas. Edge, Explorador, Steam e Gerenciador
pré-existentes geraram instruções para fechar antes da rodada. Nenhum app foi
aberto ou fechado nessa pré-checagem; não houve inferência. Inventário
indisponível é desconhecido, nunca convertido silenciosamente em ausência.

Regressão Windows após integração inicial M3/contexto e ajustes Apps:
Ruff limpo; pytest padrão 1.021 casos, 960 aprovados, 61 pulados, zero falhas.
XML privado em build/diagnostic/integration-app-gate.xml. Os pulados incluem
testes live opt-in: este resultado não substitui o ensaio interativo.

Métricas de taxa/latência/RAM/VRAM de uma nova bateria fria **não medidas** neste
incremento. Não recalcular resultados antigos usando o critério novo. O harness
não possui ownership suficiente dos apps lançados por startfile para encerrá-los
automaticamente: mantém pré-checagem, sem fechar processo por nome/PID isolado.
Cleanup de auxiliares próprios continua exigindo PID, criação e origem.

Próximo: integrar HUD e segundo incremento M3; repetir cenários elegíveis pela
interface de produção, com foco separado. Apps elevados mantêm limitação de foco.
