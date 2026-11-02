# M3 · Correções a partir do HUD/modelo reais · 02/11/2026

**Estado: em correção, gate não passou.** O baseline executou os dez cenários
três vezes: taxas20/20/10%, mediana20%. Não há BLOCKED_HARNESS nessa categoria.
[Baseline preservado](bench_browser_initial_2026-11-02.json).

O diagnóstico posterior revelou código de aba confundido com título; o detector
antigo perdeu essa afirmação. [Auditoria complementar](browser_claim_audit_2026-11-02.md).
Uma nova tentativa Normal foi recusada antes da inferência com4,29GiB livres;
isso é evidência de admissão bloqueada pelo ambiente, não prova de mínimo físico.
Nenhum app pessoal foi fechado e a proteção não foi reduzida.

No diagnóstico separado4B/Conservador, iframe e play→pause passaram1/1 cada,
com digitação nativa trusted e avanço de tempo medidos pelo observador separado.
Troca de aba inventou URL; busca e download atingiram capacidade de contexto.
Não extrapolar essa amostra para o perfil Normal ou para3execuções.

A tentativa seguinte foi interrompida após7linhas:2passes,5falhas. Cadastro
declarado concluído sem preencher os campos foi **outro falso sucesso crítico**.
O detector foi apertado para “Cadastro local concluído”, incluindo o caso em que
uma advertência separada não desfaz a afirmação anterior. O benchmark próprio
foi interrompido; prova de PID/criação fica local. Originais preservados.
Um commit também causou stash temporário de fontes durante essa tentativa;
ela não será usada como aceite, mesmo que módulos já estivessem carregados.
Próximas execuções devem ocorrer depois dos commits, com fontes estáveis.

Correções de produção: schema tipado para refs+snapshot completos; navegação
restrita à URL pedida ou links observados; troca usa IDs de tabs observadas;
valores explicitamente pedidos vinculados a labels únicos, antes de permitir
envio; conclusão de código exige leitura atual e valor observado; download exige
URL de links e pós-condição em disco; mídia exige estados reproduzindo→pausada.
Refs continuam expirando30s e conferindo identidade/documento/aba. Sem preencher
tokens omitidos na execução ou relaxar a validação. Valores ambíguos não são
vinculados automaticamente; dados da página continuam sem autoridade.

Downloads usam a sessão de rede do próprio browser, limite50MiB, mesmo origin,
publicação exclusiva sem sobrescrever, conferência de bytes/hash e confirmação
obrigatória. Download implícito por clique é negado; nada é executado. Probe de
componente recebeu36bytes exatos, sem equivaler ao aceite do planejador.
Referência primária: [protocolo CDP Network/IO](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json).

Regressão após as novas guardas:1077aprovados/65pulados/0falhas/0erros,
1142casos,41,890s; Ruff src/tests/tools/bench limpo. Isso **não substitui a nova
rodada real**, ainda pendente. Sem dependência nova. Harness pós-GC161–166MiB;
llama-server próprio chegou~3GiB RSS em execução longa. A carga fria de um token
subestima esse regime; mínimo de RAM continua desconhecido. Meta VRAM exclusiva
não é comprovada pelas amostras de uso total da GPU.

[Dados sanitizados](browser_iteration_2026-11-02.json). Não validados: dez cenários
após as últimas correções, upload/OOPIF, login pessoal, saída nos alto-falantes,
pesquisa factual com fontes e integração dos sensores. Próximo: requalificar o
formulário/abas/download, repetir10×3 com orçamento admitido e integrar AGORA.
