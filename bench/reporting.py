"""Aggregate all declared cases, including blocked coverage, without hiding failures."""
import statistics
from bench.catalog import THRESHOLDS


def summarize(rows, repetitions):
    summary = {}
    for category in sorted({row['category'] for row in rows}):
        group = [row for row in rows if row['category'] == category]
        rates = [sum(row['ok'] for row in group if row['run'] == run) /
                 len([row for row in group if row['run'] == run]) for run in range(1, repetitions+1)]
        executed = [row for row in group if row['status'] not in {'BLOCKED_HARNESS', 'BLOCKED_RUNTIME','BLOCKED_ENVIRONMENT'}]
        complete = len(executed) == len(group)
        eligible = all(row.get('gate_eligible',True) for row in group)
        median = statistics.median(rates)
        false_successes = sum(row['false_success'] for row in group)
        summary[category] = {'cases': len(group)//repetitions, 'attempts': len(group), 'executed': len(executed),
                             'blocked_harness': sum(row['status'] == 'BLOCKED_HARNESS' for row in group),
                             'blocked_runtime': sum(row['status'] == 'BLOCKED_RUNTIME' for row in group),
                             'blocked_environment':sum(row['status']=='BLOCKED_ENVIRONMENT' for row in group),
                             'focus_verified':sum(bool(row.get('focus_verified')) for row in executed),
                             'focus_measured':sum('focus_verified' in row for row in executed),
                             'pass_rates_per_run': rates,
                             'median_pass_rate': median, 'pass_rate_variance': statistics.pvariance(rates),
                             'false_successes': false_successes, 'threshold': THRESHOLDS[category],
                             'median_seconds_executed': statistics.median([r['elapsed_s'] for r in executed]) if executed else None,
                             'gate_eligible':eligible,
                             'category_gate_passed': complete and eligible and not false_successes and median >= THRESHOLDS[category]}
    return summary


def markdown_report(report):
    lines = ['# Bateria M0 — diagnóstico parcial', '',
             f"Modelo: {report['model']} · perfil: {report['profile']} · {report['runs']} execuções por caso.",
             '', 'Marcos M0–M8 não são concluídos por este relatório parcial. '
             'Apps ausentes são excluídos por inventário independente. Casos instalados bloqueados '
             'permanecem no denominador e não comprovam ausência de capacidade da Nyx. '
             'Abrir uma janela nova e obter foco são métricas distintas.', '',
             '| Categoria | Casos | Tentativas executadas | Bloqueadas no harness/ambiente | Foco confirmado/medido | Mediana de sucesso | Gate da categoria |',
             '|---|---:|---:|---:|---:|---:|---|']
    for name, row in report['summary'].items():
        lines.append(f"| {name} | {row['cases']} | {row['executed']}/{row['attempts']} | "
                     f"{row['blocked_harness']}/{row['blocked_environment']} | "
                     f"{row['focus_verified']}/{row['focus_measured']} | {row['median_pass_rate']:.1%} | "
                     f"{'passou nos casos selecionados' if row['category_gate_passed'] else 'não passou'} |")
    if report.get('excluded_apps'):
        lines.extend(['', '## Apps fora do denominador', ''])
        for excluded in report['excluded_apps']:
            lines.append(f"- {excluded['id']}: {excluded['reason']}.")
    lines.extend(['', '## Falhas e bloqueios', ''])
    failures = [row for row in report['rows'] if row['status'] not in {'PASS','BLOCKED_HARNESS'}]
    if not failures:
        lines.append('Nenhuma falha nos casos executados. Isso não avalia os casos bloqueados.')
    for row in failures:
        lines.append(f"- {row['id']}, rodada {row['run']}: {row['error_code']}; "
                     f"{row.get('error','')[:250].replace(chr(10),' ')}")
    lines.extend(['', '## Método e limites', '',
                  'TaskRunner/modelo reais; verificadores independentes leem arquivos e texto entregue. '
                  'A interface pessoal não é operada. Conferência de texto tem vocabulário limitado; '
                  'não é verificador semântico universal. Traces brutos ficam somente em logs/traces/.', '',
                  'RAM mede working sets do harness e filhos, podendo repetir páginas compartilhadas. '
                  'VRAM é uso total da GPU do sistema, não alocação exclusiva da Nyx. '
                  'Amostras a cada 250 ms podem não capturar picos mais curtos.'])
    if report.get('resumptions'):
        lines.extend(['', 'Houve retomada explícita: linhas concluídas foram preservadas; '
                      'somente casos de leitura/conversa podem ser retomados automaticamente. '
                      'Uma execução foi interrompida durante leitura e uma gravação encontrou '
                      'WinError5 transitório; o salvamento agora é atômico, com tentativa limitada.'])
    return '\n'.join(lines) + '\n'
