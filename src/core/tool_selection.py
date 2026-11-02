"""Apply explicit user constraints to the planner catalog, never observations."""
import re


def select_task_tools(goal, tools):
    # This is catalog narrowing only. Registry permissions remain authoritative.
    # Negated delegation must not remain available just because a model ignores prose.
    no_delegation = re.search(r'\b(?:n[aã]o\s+delegue|sem\s+(?:microagentes|subagentes|delegar))\b',
                              goal, re.IGNORECASE)
    selected = [tool for tool in tools if not (no_delegation and tool['name'] == 'agent_team')]
    from core.app_grounding import explicit_app_target
    if explicit_app_target(goal):
        # A simple app launch must not expose the arithmetic calculator or web
        # as interchangeable actions. Execution/confirmation still use registry policy.
        return [tool for tool in selected if tool['name'] == 'ui_action']
    file_arithmetic = (re.search(r'\b(?:leia|ler|read)\b', goal, re.IGNORECASE)
                       and re.search(r'\b(?:arquivos?|files?)\b|\.txt\b', goal, re.IGNORECASE)
                       and re.search(r'\b(?:soma|some|somar|média|calcule|sum)\b', goal, re.IGNORECASE))
    # Negative delegation wording is not a request for a second kind of work.
    without_negative = re.sub(r'\bn[aã]o\s+delegue\b', '', goal, flags=re.IGNORECASE)
    other_work = re.search(r'\b(?:pesquis\w*|salv\w*|escrev\w*|envi\w*|abr\w*|navegador|microagentes|subagentes|deleg\w*|código|aprenda)\b',
                           without_negative, re.IGNORECASE)
    if file_arithmetic and not other_work:
        relevant = [tool for tool in selected if tool['name'] in {'read_file', 'find_files', 'calculator'}]
        if relevant:
            return relevant
    return selected
