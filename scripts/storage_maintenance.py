from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISK_LIMIT_GB = 10.0

CLEANUP_TARGETS = {
    "app_backups": {
        "path": PROJECT_ROOT / "data" / "backups",
        "patterns": ("*.enc", "*.sqlite", "*.sqlite3", "*.db", "*.json", "*.zip"),
        "normal_days": 7,
        "soft_days": 3,
        "hard_min_keep": 3,
        "normal_min_keep": 8,
    },
    "audit_logs": {
        "path": PROJECT_ROOT / "data" / "logs",
        "patterns": ("*.enc", "*.jsonl", "*.log", "*.txt"),
        "normal_days": 45,
        "soft_days": 21,
        "hard_min_keep": 3,
        "normal_min_keep": 8,
    },
    "vm_backups": {
        "path": PROJECT_ROOT / "vm_backups",
        "patterns": ("*.sqlite", "*.sqlite3", "*.db", "*.zip", "*.enc"),
        "normal_days": 14,
        "soft_days": 7,
        "hard_min_keep": 3,
        "normal_min_keep": 5,
    },
    "exports": {
        "path": PROJECT_ROOT / "exports",
        "patterns": ("*.zip",),
        "normal_days": 14,
        "soft_days": 3,
        "hard_min_keep": 1,
        "normal_min_keep": 3,
    },
}

PROTECTED_NAMES = {
    "secrets.toml",
    "admin_paes.sqlite",
    "panel_admin.sqlite",
}


@dataclass(frozen=True)
class Candidate:
    path: Path
    group: str
    size: int
    modified_at: datetime

    @property
    def age_days(self) -> float:
        return (datetime.now(timezone.utc) - self.modified_at).total_seconds() / 86400


def bytes_to_human(value: int | float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def resolve_inside_project(path: Path) -> Path:
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Ruta fuera del proyecto bloqueada: {resolved}") from exc
    return resolved


def allowed_targets() -> dict[str, dict[str, object]]:
    targets: dict[str, dict[str, object]] = {}
    for name, config in CLEANUP_TARGETS.items():
        target_path = resolve_inside_project(config["path"])  # type: ignore[arg-type]
        targets[name] = {**config, "path": target_path}
    return targets


def collect_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    for group, config in allowed_targets().items():
        target_path: Path = config["path"]  # type: ignore[assignment]
        if not target_path.exists():
            continue
        for pattern in config["patterns"]:  # type: ignore[index]
            for item in target_path.glob(str(pattern)):
                item = resolve_inside_project(item)
                if not item.is_file():
                    continue
                if item.name in PROTECTED_NAMES:
                    continue
                stat = item.stat()
                candidates.append(
                    Candidate(
                        path=item,
                        group=group,
                        size=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                    )
                )
    return candidates


def repo_size_bytes() -> int:
    total = 0
    for item in PROJECT_ROOT.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def disk_snapshot(disk_limit_gb: float) -> dict[str, object]:
    usage = shutil.disk_usage(PROJECT_ROOT)
    configured_limit = int(disk_limit_gb * 1024**3)
    project_used = repo_size_bytes()

    # On the 10 GB VM the filesystem total is close to the configured limit, so
    # real disk usage is the right signal. On a developer laptop with a much
    # larger disk, compare only the project footprint against the VM budget.
    if configured_limit > 0 and usage.total > configured_limit * 2:
        effective_total = configured_limit
        used = min(project_used, effective_total)
        basis = "project"
    else:
        effective_total = min(usage.total, configured_limit) if configured_limit > 0 else usage.total
        used = min(usage.used, effective_total)
        basis = "filesystem"

    return {
        "filesystem_total": float(usage.total),
        "filesystem_used": float(usage.used),
        "effective_limit": float(effective_total),
        "effective_used": float(used),
        "project_used": float(project_used),
        "effective_ratio": float(used / effective_total) if effective_total else 0.0,
        "basis": basis,
    }


def select_by_retention(candidates: list[Candidate], *, soft_mode: bool) -> list[Candidate]:
    now = datetime.now(timezone.utc)
    selected: list[Candidate] = []
    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.group, []).append(candidate)

    targets = allowed_targets()
    for group, items in grouped.items():
        config = targets[group]
        keep_count = int(config["hard_min_keep"] if soft_mode else config["normal_min_keep"])
        age_days = int(config["soft_days"] if soft_mode else config["normal_days"])
        cutoff = now - timedelta(days=age_days)
        newest_first = sorted(items, key=lambda item: item.modified_at, reverse=True)
        protected_latest = {item.path for item in newest_first[:keep_count]}
        for item in newest_first[keep_count:]:
            if item.path in protected_latest:
                continue
            if item.modified_at < cutoff:
                selected.append(item)
    return sorted(selected, key=lambda item: item.modified_at)


def select_hard_pressure(
    candidates: list[Candidate],
    already_selected: set[Path],
    *,
    current_used: float,
    effective_limit: float,
    target_threshold: float,
) -> list[Candidate]:
    grouped: dict[str, list[Candidate]] = {}
    targets = allowed_targets()
    for candidate in candidates:
        if candidate.path in already_selected:
            continue
        grouped.setdefault(candidate.group, []).append(candidate)

    protected: set[Path] = set()
    for group, items in grouped.items():
        keep_count = int(targets[group]["hard_min_keep"])
        newest_first = sorted(items, key=lambda item: item.modified_at, reverse=True)
        protected.update(item.path for item in newest_first[:keep_count])

    pressure_candidates = sorted(
        [item for item in candidates if item.path not in already_selected and item.path not in protected],
        key=lambda item: item.modified_at,
    )
    target_used = effective_limit * target_threshold
    selected: list[Candidate] = []
    projected_used = current_used
    for item in pressure_candidates:
        if projected_used <= target_used:
            break
        selected.append(item)
        projected_used -= item.size
    return selected


def remove_files(files: list[Candidate], *, dry_run: bool) -> tuple[int, int, list[str]]:
    deleted_count = 0
    deleted_bytes = 0
    errors: list[str] = []
    for item in files:
        try:
            if not dry_run:
                item.path.unlink(missing_ok=True)
            deleted_count += 1
            deleted_bytes += item.size
        except OSError as exc:
            errors.append(f"{item.path}: {exc}")
    return deleted_count, deleted_bytes, errors


def cleanup_empty_dirs() -> None:
    for config in allowed_targets().values():
        root: Path = config["path"]  # type: ignore[assignment]
        if not root.exists():
            continue
        for item in sorted(root.rglob("*"), key=lambda value: len(value.parts), reverse=True):
            if item.is_dir():
                try:
                    item.rmdir()
                except OSError:
                    pass


def run(args: argparse.Namespace) -> dict[str, object]:
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_before = disk_snapshot(args.disk_limit_gb)
    candidates = collect_candidates()
    soft_mode = snapshot_before["effective_ratio"] >= args.soft_threshold
    selected = select_by_retention(candidates, soft_mode=soft_mode)

    if snapshot_before["effective_ratio"] >= args.hard_threshold:
        selected.extend(
            select_hard_pressure(
                candidates,
                {item.path for item in selected},
                current_used=snapshot_before["effective_used"],
                effective_limit=snapshot_before["effective_limit"],
                target_threshold=args.target_threshold,
            )
        )

    selected = sorted({item.path: item for item in selected}.values(), key=lambda item: item.modified_at)
    deleted_count, deleted_bytes, errors = remove_files(selected, dry_run=args.dry_run)
    if not args.dry_run:
        cleanup_empty_dirs()
    snapshot_after = disk_snapshot(args.disk_limit_gb)

    return {
        "dry_run": args.dry_run,
        "root": str(PROJECT_ROOT),
        "soft_mode": soft_mode,
        "before": snapshot_before,
        "after": snapshot_after,
        "candidates": len(candidates),
        "selected": len(selected),
        "deleted_count": deleted_count,
        "deleted_bytes": deleted_bytes,
        "deleted_human": bytes_to_human(deleted_bytes),
        "errors": errors,
        "files": [str(item.path.relative_to(PROJECT_ROOT)) for item in selected[: args.preview_limit]],
        "truncated_files": max(0, len(selected) - args.preview_limit),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Limpia backups/logs antiguos del Panel PAES sin tocar SQLite vivo, secrets ni assets.",
    )
    parser.add_argument("--disk-limit-gb", type=float, default=DEFAULT_DISK_LIMIT_GB)
    parser.add_argument("--soft-threshold", type=float, default=0.80)
    parser.add_argument("--hard-threshold", type=float, default=0.90)
    parser.add_argument("--target-threshold", type=float, default=0.75)
    parser.add_argument("--preview-limit", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="Muestra que se borraria, sin borrar archivos.")
    parser.add_argument("--json", action="store_true", help="Imprime resumen JSON para monitoreo.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    before = result["before"]
    after = result["after"]
    print("Panel PAES storage maintenance")
    print(f"Modo: {'dry-run' if result['dry_run'] else 'aplicar'}")
    print(
        "Uso efectivo antes: "
        f"{bytes_to_human(before['effective_used'])} / {bytes_to_human(before['effective_limit'])} "
        f"({before['effective_ratio']:.1%})"
    )
    print(
        "Uso efectivo despues: "
        f"{bytes_to_human(after['effective_used'])} / {bytes_to_human(after['effective_limit'])} "
        f"({after['effective_ratio']:.1%})"
    )
    print(f"Archivos candidatos: {result['candidates']}")
    print(f"Archivos seleccionados: {result['selected']}")
    print(f"Espacio liberado: {result['deleted_human']}")
    for file_name in result["files"]:
        print(f"- {file_name}")
    if result["truncated_files"]:
        print(f"... {result['truncated_files']} archivo(s) mas")
    if result["errors"]:
        print("Errores:")
        for error in result["errors"]:
            print(f"- {error}")


if __name__ == "__main__":
    main()
