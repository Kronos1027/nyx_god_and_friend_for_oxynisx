import pytest

from core.windows_sandbox import run_lpac


@pytest.mark.parametrize("field,value", [
    ("timeout", float("nan")), ("timeout", float("inf")), ("timeout", True),
    ("timeout", 0), ("timeout", 301), ("timeout", "20"),
    ("memory_mib", 63), ("memory_mib", 513), ("memory_mib", 64.5),
    ("output_limit", -1), ("output_limit", 0), ("output_limit", True),
    ("output_limit", float("inf")), ("output_limit", 1024 * 1024 + 1),
    ("cpu_percent", 0), ("cpu_percent", 51), ("cpu_percent", 5.5),
    ("process_limit", 0), ("process_limit", 5), ("process_limit", True),
])
def test_invalid_limits_rejected_before_accessing_container(field, value):
    # None ensures validation precedes API access and any process creation.
    with pytest.raises(ValueError, match="Limite inválido"):
        run_lpac(None, None, [], None, **{field: value})
