"""Launch the share package through stdio using this installation's settings."""
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    settings_path = Path(__file__).resolve().with_name("bridge-settings.json")
    required = ("SWLOCAL_TEMP", "SWLOCAL_OUTPUT", "SWLOCAL_TYPELIB")
    if not all(os.environ.get(key) for key in required) and settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            if not isinstance(settings, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in settings.items()
            ):
                raise ValueError("expected a map of text settings")
            for key, value in settings.items():
                os.environ.setdefault(key, value)
        except (OSError, ValueError) as error:
            raise SystemExit(f"Could not read {settings_path}: {error}. Run install.ps1 again.") from error
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit("Run install.ps1 on this computer. Missing settings: " + ", ".join(missing))
    scratch = Path(os.environ["SWLOCAL_TEMP"]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(scratch), TMP=str(scratch), SWLOCAL_TEMP=str(scratch))
    tempfile.tempdir = str(scratch)
    sys.dont_write_bytecode = True

    from swlocal.server import main as serve

    serve()


if __name__ == "__main__":
    main()
