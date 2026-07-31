from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from panel.student_graphs import load_student_score_series, render_student_graph_png, update_all_student_graphs
from scripts.import_essay_scores import load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera y sube graficos individuales a la tarjeta Grafico de la lista Ensayos usando SQLite como fuente."
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra cuantos graficos se generarian; no escribe en Trello.")
    parser.add_argument("--limit", type=int, default=None, help="Limita la cantidad de boards procesados.")
    parser.add_argument("--delay", type=float, default=0.15, help="Pausa entre boards para cuidar rate limits.")
    parser.add_argument("--include-archived", action="store_true", help="Incluye alumnos archivados en la base local.")
    args = parser.parse_args()

    if args.dry_run:
        series = load_student_score_series(active_only=not args.include_archived)
        if args.limit is not None:
            series = series[: max(0, args.limit)]
        generated = 0
        skipped = 0
        for item in series:
            if len(item.points) < 2:
                skipped += 1
                print(f"[SKIP] {item.student_name}: datos insuficientes")
                continue
            render_student_graph_png(item)
            generated += 1
            print(f"[OK] {item.student_name}: {len(item.points)} punto(s), ultimo ensayo {item.points[-1][0]}")
        print(f"Graficos generables: {generated}")
        print(f"Omitidos: {skipped}")
        return

    config = load_config()
    result = update_all_student_graphs(
        config,
        limit=args.limit,
        delay=max(args.delay, 0),
        active_only=not args.include_archived,
    )
    print(result)


if __name__ == "__main__":
    main()

