"""Create a portable, slash-separated ZIP for embedding in the Windows installer."""
from pathlib import Path
import sys
import zipfile


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
