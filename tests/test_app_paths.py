import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app_paths import project_root, resource_path, user_data_dir


def test_development_paths_resolve_inside_repository():
    root = Path(__file__).resolve().parent.parent
    assert project_root() == root
    assert user_data_dir() == root
    assert resource_path("src/core/schema.gbnf") == root / "src/core/schema.gbnf"
