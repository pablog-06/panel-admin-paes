from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from panel.crypto import DATA_ENCRYPTION_KEY_NAME, generate_data_encryption_key  # noqa: E402


def main() -> None:
    print("# Copia esta linea en .streamlit/secrets.toml")
    print("# No la subas a GitHub y no la compartas.")
    print(f'{DATA_ENCRYPTION_KEY_NAME} = "{generate_data_encryption_key()}"')


if __name__ == "__main__":
    main()
