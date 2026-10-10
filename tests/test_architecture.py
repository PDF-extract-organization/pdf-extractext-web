"""Regla de dependencias entre capas, comprobada con `ast` (ver tests/architecture.py).

1. application solo importa la biblioteca estándar y app.application.
2. presentation no importa app.infrastructure: pasa por app.dependencies.
3. infrastructure no importa presentation, dependencies ni main.
"""

import pytest

from tests.architecture import (
    APP,
    application_violations,
    forbidden_violations,
    imported_modules,
    layer_files,
)


def relative(path) -> str:
    return path.relative_to(APP).as_posix()


def imports_of(path) -> set[str]:
    return imported_modules(path.read_text(encoding="utf-8"))


# --- La regla, aplicada al código del servicio ---


@pytest.mark.parametrize("layer", ["application", "infrastructure", "presentation"])
def test_cada_capa_tiene_archivos_que_comprobar(layer):
    assert layer_files(layer), f"app/{layer} está vacía: la regla no comprobaría nada"


@pytest.mark.parametrize("path", layer_files("application"), ids=relative)
def test_application_solo_importa_la_biblioteca_estandar_y_a_si_misma(path):
    assert application_violations(imports_of(path)) == set()


@pytest.mark.parametrize("path", layer_files("presentation"), ids=relative)
def test_presentation_no_importa_la_infraestructura(path):
    assert forbidden_violations(imports_of(path), {"app.infrastructure"}) == set()


@pytest.mark.parametrize("path", layer_files("infrastructure"), ids=relative)
def test_infrastructure_no_importa_capas_superiores_ni_el_cableado(path):
    forbidden = {"app.presentation", "app.dependencies", "app.main"}

    assert forbidden_violations(imports_of(path), forbidden) == set()


# --- El comprobador detecta lo que debe ---


def test_detecta_librerias_externas_en_application():
    source = "import httpx\nfrom pydantic import BaseModel"

    assert application_violations(imported_modules(source)) == {"httpx", "pydantic"}


def test_detecta_otra_capa_en_application():
    source = "from app.infrastructure.mongo import Repo"

    assert application_violations(imported_modules(source)) == {"app.infrastructure.mongo"}


def test_permite_la_biblioteca_estandar_y_la_propia_capa():
    source = (
        "import re\n"
        "from dataclasses import dataclass\n"
        "from app.application.entities import Summary"
    )

    assert application_violations(imported_modules(source)) == set()


def test_detecta_un_import_prohibido_entre_capas():
    modules = imported_modules("from app.infrastructure.db import Repo")

    assert forbidden_violations(modules, {"app.infrastructure"}) == {"app.infrastructure.db"}


def test_no_confunde_un_paquete_con_otro_que_empieza_igual():
    assert forbidden_violations({"app.infrastructure_extra"}, {"app.infrastructure"}) == set()
