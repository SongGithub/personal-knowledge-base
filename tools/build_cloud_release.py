#!/usr/bin/env python3
"""Build a Lambda code-only ZIP from pinned Linux wheels and explicit sources."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


REPOSITORY = Path(__file__).resolve().parents[1]


def build(output: Path):
    output = output.expanduser().resolve()
    if output.suffix != ".zip":
        raise ValueError("Output must be a ZIP path")
    with tempfile.TemporaryDirectory(prefix="pkb-lambda-") as directory:
        stage = Path(directory) / "package"
        subprocess.run([
            sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
            "--require-hashes", "--only-binary=:all:", "--no-compile",
            "--platform", "manylinux2014_x86_64", "--python-version", "3.12",
            "--implementation", "cp", "--abi", "cp312", "--target", str(stage),
            "-r", str(REPOSITORY / "requirements-cloud.lock"),
        ], check=True)
        source = stage / "cloud_kb"
        source.mkdir()
        for path in sorted((REPOSITORY / "cloud_kb").glob("*.py")):
            shutil.copyfile(path, source / path.name)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                relative = path.relative_to(stage)
                if "__pycache__" in relative.parts or relative.parts[0] == "bin" or path.suffix == ".pyc":
                    continue
                if path.is_symlink():
                    raise ValueError("Release staging contains a symlink")
                if not path.is_file():
                    continue
                info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
    print("Release SHA-256:", hashlib.sha256(output.read_bytes()).hexdigest())
    print("Release bytes:", output.stat().st_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    build(parser.parse_args().output)
