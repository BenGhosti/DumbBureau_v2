from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TESTS = [
    "test_crypto.py",
    "test_auth_flow.py",
    "test_tasks.py",
    "test_categories_templates.py",
    "test_pdf.py",
    "test_admin.py",
    "test_security.py",
    "test_proxy_config.py",
]


def main() -> int:
    base = Path(__file__).resolve().parent
    failed: list[str] = []
    for name in TESTS:
        print(f"\n===== {name} =====")
        result = subprocess.run([sys.executable, str(base / name)])
        if result.returncode != 0:
            failed.append(name)

    print("\n===== SUMMARY =====")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
