from __future__ import annotations

from typing import Any


BOARD_LISTS: list[dict[str, Any]] = [
    {
        "id": "global-results",
        "name": "Resultados globales",
        "kind": "locked",
        "stats": {
            "exam": "Ultimo ensayo",
            "average": "742",
            "median": "751",
            "stddev": "68",
            "min": {"score": "612", "student": "Martina A. (demo)"},
            "max": {"score": "894", "student": "Benjamin R. (demo)"},
        },
        "note": (
            "Estadisticas agregadas de muestra. No se accede a resultados "
            "individuales reales ni se modifica informacion de alumnos."
        ),
        "cards": [],
    },
    {"id": "chemistry", "name": "Quimica", "cards": []},
    {"id": "physics", "name": "Fisica", "cards": []},
    {"id": "biology", "name": "Biologia", "cards": []},
    {"id": "scientific-method", "name": "Metodo cientifico", "cards": []},
]
