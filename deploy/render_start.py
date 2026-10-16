"""Initialize a fresh Render disk, then run Atlas without root privileges."""

import os
from pathlib import Path
import sys


def main():
    directory = Path(os.environ.get("ATLAS_DATA_DIR", "/data/atlas"))
    directory.mkdir(parents=True, exist_ok=True)
    os.chown(directory, 10001, 10001)
    directory.chmod(0o700)
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
    os.execv(sys.executable, [sys.executable, "/app/app.py"])


if __name__ == "__main__":
    main()
