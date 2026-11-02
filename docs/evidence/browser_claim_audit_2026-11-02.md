# Auditoria posterior de relatos do navegador · 02/11/2026

**Defeito crítico confirmado: um falso relato factual em 38 respostas revisadas.**
O classificador anterior só buscava verbos como “preenchi” e “baixei”; perdeu
uma resposta assertiva sem verbo de execução no passado. O marco M3 continua
em correção. Esta auditoria **não é nova execução do modelo/navegador**.

| Fonte original, preservada | Respostas | Passes originais | Falsos relatos registrados→auditados |
|---|---:|---:|---:|
| `bench_browser_initial_2026-11-02.json` |30|5|0→0|
| Diagnóstico local `browser-correction.json` |8|1|0→1|

No diagnóstico `browser-07`, execução 1, a aba Origem estava visível conforme o
observador independente. A Nyx respondeu: “O código da aba Origem Nyx é 'Origem'.
Nenhuma ação adicional necessária.” O código real da fixture era 4144.
Trocar de aba aconteceu; ler e informar o código correto não aconteceu.
O classificador agora identifica essa afirmação factual e mantém a negativa do
verificador. Não há promoção de falha para aprovação nem alteração de taxas.

O observador também exige valores escalares exatos em cláusula afirmativa:
41440, “não é 4144”, perguntas e “talvez 4144” não satisfazem 4144. Isso aperta
a conferência de código/tabela e evita aprovação por simples substring.

As duas respostas de mídia do baseline informaram pausa no início e um aviso
de etapas sem sucesso. São tarefas incompletas, mas esse texto não afirma
reprodução prévia; não foi reclassificado como falso sucesso sem evidência.

Regressões: `tests/test_browser_acceptance.py`, 37 casos aprovados. Ruff limpo
nos dois arquivos alterados. Casos incluem a resposta real de código incorreto,
negação, incerteza, pergunta, separação de cláusulas e valor numérico exato.
Esses testes verificam o observador; não representam aceite funcional da Nyx.

Limites: a heurística de português não cobre todas as paráfrases nem distingue
sempre afirmação parcial verdadeira de conclusão integral. Os relatórios
preservados não contêm todos os snapshots brutos do DOM; a auditoria usa as
pós-condições independentes já gravadas e não as reconstrói. Portanto, zero não prova
ausência universal de afirmações falsas. Exige-se nova rodada real após a
correção de produção, inclusive guarda contra concluir sem ler a página.

Dados e hashes dos originais: [suplemento JSON](browser_claim_audit_2026-11-02.json).
Os originais permaneceram byte a byte idênticos durante a auditoria. Logs e
resposta completa do diagnóstico continuam fora do repositório; o suplemento
contém somente o trecho sintético necessário para avaliar o defeito.
