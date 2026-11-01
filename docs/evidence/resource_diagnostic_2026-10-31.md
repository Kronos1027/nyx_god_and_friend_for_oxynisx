# Diagnóstico de memória sob demanda — 31/10/2026

## Problema observado

Os ensaios de arquivos conversation_planner_regression e conversation_planner_retry
pararam por RAM0,86/0,90GiB. A recusa era correta, mas só orientava aguardar.
Agora o aviso indica Personalizar → Modelo local → Diagnosticar memória.
O diálogo consulta RAM/VRAM sem inferência e oferece um botão explícito para
consultar nomes/working sets dos processos. Não monitora continuamente nem
habilita o sensor de Presença; não envia a lista ao modelo ou à auditoria.
Abrir o diagnóstico por si só não consulta nomes. Nenhum aplicativo é fechado.

## Medição real

`tools/diagnose_resources.py --processes --ui` usa o diálogo e worker Qt de
produção numa janela isolada fora da tela. `resource_diagnostic_ui_2026-10-31.json`:

- 317 processos consultados, um sem medida; consulta completa, sem truncamento.
- Consulta dos processos em 391 ms; recursos e processos em 484 ms; entrega
  ao diálogo em 500 ms, seis linhas com os valores observados.
- RAM1,16GiB livre e VRAM7,33GiB livre nesse instante. A elegibilidade crítica
  não garante que um modelo frio caiba no orçamento de carga.
- Working sets agrupados observados: Opera4,58GiB, ChatGPT2,61GiB,
  llama-server2,07GiB. Não são memória privada exclusiva nem previsão de quanto
  seria liberado ao fechar algo. Páginas compartilhadas podem ser contadas duas vezes.

O estado e a captura local build/previews/resource-diagnostics.png foram
inspecionados. O teste não opera o navegador pessoal, não fecha processos e não
altera modelo ou perfil. O comando CLI só grava nomes se executado explicitamente
com --processes; a interface não persiste esses dados automaticamente.

## Falhas intermediárias e limites

- Orçamento inicial de 250 ms retornou somente 90/131 processos e marcou
  truncated=true. Artefatos resource_diagnostic e resource_diagnostic_retry
  preservados. A UI identifica consulta parcial; nenhum parcial é apresentado
  como inventário completo. Limite final aumentado para 1 s, fora da thread
  visual; a medição final concluiu em 391 ms. Continua sendo um prazo cooperativo
  entre chamadas do SO, não timeout rígido de cada syscall.
- A primeira execução CLI gravou JSON corretamente, mas falhou ao imprimir a
  seta Unicode em stdout cp1252. Console agora usa escapes ASCII no JSON; arquivo
  permanece UTF-8 e a UI mantém PT-BR. Driver de arquivos recebeu a mesma correção
  de impressão, sem mudar pontuação ou verificadores.
- Dados podem ficar indisponíveis por permissões/processos encerrados. Não há
  enumeração de linhas de comando, caminhos, títulos de janela ou ambiente.
- O diagnóstico não libera RAM nem resolve a disputa de recursos com outros
  programas. Reservas e descarga automática já existente dos modelos ociosos da
  Nyx continuam; não foi acrescentado encerramento automático de aplicativos.

Antes: zero consumidores acessíveis a partir do aviso. Depois: diálogo próprio
com seis grupos observados e tempo de consulta registrado, sem usar LLM. A
capacidade de completar a tarefa de oito arquivos ainda depende da RAM disponível.

Referência primária: [psutil — process_iter e RSS](https://psutil.readthedocs.io/stable/).

Regressão final: 913 aprovados, 27 pulados, zero falhas, 52,136 s, saída 0;
Ruff limpo, navegador/Windows reais habilitados. LPAC opt-in pulado. Fonte local:
build/diagnostic/resource-diagnostics-final.xml. Pet/overlay preservados.
