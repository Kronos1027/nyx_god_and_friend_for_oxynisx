# Escada para "abrir app X"
1. Normalizar nome (sem acento, minúsculas), expandir aliases ("navegador/browser" → Chrome, Edge, Firefox, Brave, na ordem do navegador padrão; "zap" → WhatsApp; "code" → Visual Studio Code; "explorador" → Explorador de Arquivos; "calculadora/calculator").
2. Já aberto? (janelas visíveis + processos) → focar (`ShowWindow(SW_RESTORE)` + `AttachThreadInput` + `SetForegroundWindow`) e reportar.
3. Catálogo exato → prefixo/token → fuzzy (limiar com folga sobre o 2º lugar). Ambíguo → erro tipado com top-5, nunca chute.
4. Lançar (lnk / AUMID / exe do catálogo). Esperar janela por sinais múltiplos (até 20 s, poll adaptativo, cancelável).
5. Falhou: tentar próxima fonte do catálogo para o mesmo app (ex.: lnk → AUMID).
6. Último recurso, **com confirmação**: tecla Win → digitar nome → Enter; verificar janela.
7. Ainda falhou: resposta honesta com o que foi tentado, o último erro real e uma sugestão ("posso procurar o instalador?").
Sinais de janela nova: pid em descendentes do pid lançado; exe sob a pasta de instalação; título com tokens significativos (ignorar microsoft/google/windows/app/studio); classe conhecida; `ApplicationFrameHost` com título do app.
