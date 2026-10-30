"""Bounded decimal arithmetic; no expressions, eval, code or external effects."""
from decimal import Decimal, DecimalException, Inexact, localcontext
import json
import re

from tools.registry import ToolResult


def calculator_contract():
    return {"operation": "sum|subtract|product|divide|mean|min|max",
            "values": "Lista de 1–128 números observados; strings decimais preservam precisão. Use ponto decimal.",
            "rules": "subtract/divide exigem 2 valores. Use para calcular, não estime o resultado mentalmente."}


def calculate(params):
    operation, values = params.get("operation"), params.get("values")
    if operation not in {"sum", "subtract", "product", "divide", "mean", "min", "max"}:
        return ToolResult(False, error="Operação inválida: sum, subtract, product, divide, mean, min, max.")
    if not isinstance(values, list) or not 1 <= len(values) <= 128:
        return ToolResult(False, error="values deve conter de 1 a 128 números.")
    if operation in {"subtract", "divide"} and len(values) != 2:
        return ToolResult(False, error="subtract e divide exigem exatamente dois valores.")
    numbers = []
    for value in values:
        if type(value) not in (str, int, float) or not re.fullmatch(
                r"[+-]?\d{1,32}(?:\.\d{1,32})?(?:[eE][+-]?\d{1,2})?", str(value)):
            return ToolResult(False, error="Use somente números finitos com ponto decimal, sem expressões ou código.")
        numbers.append(Decimal(str(value)))
    try:
        with localcontext() as context:
            context.prec, context.Emax, context.Emin = 80, 256, -256
            if operation in {"sum", "mean"}:
                result = sum(numbers, Decimal(0))
                if operation == "mean":
                    result /= len(numbers)
            elif operation == "subtract":
                result = numbers[0] - numbers[1]
            elif operation == "divide":
                result = numbers[0] / numbers[1]
            elif operation == "product":
                result = Decimal(1)
                for number in numbers:
                    result *= number
            else:
                result = min(numbers) if operation == "min" else max(numbers)
            rounded = context.flags[Inexact]
            if not result.is_finite():
                raise ValueError("Resultado não finito")
            answer = format(result, "f")
            if "." in answer:
                answer = answer.rstrip("0").rstrip(".")
            if len(answer) > 600:
                raise ValueError("Resultado excede o limite")
    except (DecimalException, ValueError) as exc:
        return ToolResult(False, error=f"Cálculo não concluído: divisão por zero ou limite numérico ({type(exc).__name__}).")
    report = {"result": answer, "operation": operation, "rounded": rounded,
              "precision_digits": 80, "values": [str(number) for number in numbers]}
    return ToolResult(True, json.dumps(report, ensure_ascii=False, separators=(",", ":")), meta=report)
