"""Comprobador de la regla de dependencias entre capas, con `ast` y sin dependencias nuevas.

Solo mira imports directos y absolutos: no detecta dependencias indirectas.
"""

import ast
import sys
from collections.abc import Iterable
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"


def layer_files(layer: str) -> list[Path]:
    return sorted((APP / layer).rglob("*.py"))


def imported_modules(source: str) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _is_within(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def application_violations(modules: Iterable[str]) -> set[str]:
    """Lo que la capa de aplicación importa sin poder: todo salvo stdlib y ella misma."""
    return {
        module
        for module in modules
        if not _is_within(module, "app.application")
        and module.split(".")[0] not in sys.stdlib_module_names
    }


def forbidden_violations(modules: Iterable[str], forbidden: set[str]) -> set[str]:
    return {m for m in modules if any(_is_within(m, f) for f in forbidden)}
