from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from panel.auth import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera hashes PBKDF2 para usuarios del Panel PAES."
    )
    parser.add_argument(
        "users",
        nargs="+",
        help="Nombres de usuario. Usa al menos dos, por ejemplo: admin coordinacion",
    )
    args = parser.parse_args()

    unique_users = []
    seen = set()
    for username in args.users:
        normalized = username.strip().lower()
        if normalized and normalized not in seen:
            unique_users.append(normalized)
            seen.add(normalized)

    if len(unique_users) < 2:
        raise SystemExit("Debes indicar al menos dos usuarios distintos.")

    print("# Copia este bloque en .streamlit/secrets.toml")
    print("# No pegues aqui contrasenas en texto plano.")
    for username in unique_users:
        while True:
            password = getpass.getpass(f"Contrasena para {username}: ")
            confirmation = getpass.getpass(f"Repite contrasena para {username}: ")
            if password != confirmation:
                print("Las contrasenas no coinciden. Intenta nuevamente.", file=sys.stderr)
                continue
            if len(password) < 12:
                print("Usa al menos 12 caracteres.", file=sys.stderr)
                continue
            break

        print()
        print(f"[auth.users.{username}]")
        print(f'name = "{username}"')
        print(f'password_hash = "{hash_password(password)}"')


if __name__ == "__main__":
    main()
