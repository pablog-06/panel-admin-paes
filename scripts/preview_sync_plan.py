from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from panel.student_sync import build_student_sync_plan
from panel.trello_client import TrelloReadOnlyError
from scripts.import_essay_scores import load_config


def main() -> None:
    config = load_config()
    try:
        plan = build_student_sync_plan(config, [])
    except TrelloReadOnlyError as error:
        raise SystemExit(str(error)) from error

    actions = plan.get("actions", [])
    print("Fuente: master local SQLite")
    print("Destino: boards PAES de alumnos")
    print("Modo: vista previa, no escribe en Trello.")
    print("Regla: Ensayos no se modifica.")
    print()
    print(f"Alumnos: {plan.get('students', 0)}")
    print(f"Cambios pendientes: {len(actions)}")
    print(f"Errores: {len(plan.get('errors', []))}")
    print()

    if plan.get("summary"):
        print("Resumen:")
        for action_name, count in sorted(plan["summary"].items()):
            print(f"- {action_name}: {count}")
        print()

    for index, action in enumerate(actions[:50], start=1):
        target = action.get("list_name") or ""
        if action.get("card_title"):
            target = f"{target} / {action['card_title']}".strip()
        print(f"{index}. {action.get('action')} | {action.get('student_name')} | {target}")
        print(f"   {action.get('detail', '')}")

    if len(actions) > 50:
        print(f"... {len(actions) - 50} acciones mas.")


if __name__ == "__main__":
    main()
