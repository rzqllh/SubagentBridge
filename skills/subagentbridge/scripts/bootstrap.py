"""Install/update the SubagentBridge runtime and register it globally in Antigravity.

This script intentionally keeps the runtime outside the active workspace so one
installation can serve every Antigravity project.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

DEFAULT_SOURCE = "git+https://github.com/rzqllh/SubagentBridge.git"
DEFAULT_CONFIG = Path.home() / ".gemini" / "config" / "mcp_config.json"
DEFAULT_RUNTIME = Path.home() / ".subagentbridge" / "runtime"
DEFAULT_DB = Path.home() / ".subagentbridge" / "sessions.db"


def runtime_python(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "Scripts" / "python.exe"
    return runtime_dir / "bin" / "python"


def load_config(path: Path) -> dict:
    if not path.exists():
        return {"mcpServers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Refusing to modify invalid JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Refusing to modify non-object JSON at {path}")
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise SystemExit(f"mcpServers must be an object in {path}")
    return data


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="mcp_config.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap SubagentBridge for Antigravity")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="pip-installable package source")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Antigravity MCP config path")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME, help="isolated runtime venv")
    parser.add_argument("--dry-run", action="store_true", help="show planned paths without changing anything")
    args = parser.parse_args()

    config_path = args.config.expanduser().resolve()
    runtime_dir = args.runtime_dir.expanduser().resolve()
    db_path = DEFAULT_DB.expanduser().resolve()
    python_exe = runtime_python(runtime_dir)

    print(f"SubagentBridge runtime: {runtime_dir}")
    print(f"Antigravity MCP config: {config_path}")
    print(f"Package source: {args.source}")

    agy = shutil.which("agy")
    if agy:
        try:
            version = subprocess.check_output([agy, "--version"], text=True, stderr=subprocess.STDOUT).strip()
        except Exception:
            version = "unknown"
        print(f"agy: {agy} ({version})")
    else:
        print("warning: agy CLI not found; the MCP server can install, but runner='agy' will not execute")

    if args.dry_run:
        return 0

    runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    if not python_exe.exists():
        print("Creating isolated Python runtime...")
        venv.EnvBuilder(with_pip=True, clear=False).create(runtime_dir)

    print("Installing/updating SubagentBridge runtime...")
    subprocess.run(
        [str(python_exe), "-m", "pip", "install", "--upgrade", args.source],
        check=True,
    )

    # Verify imports before touching Antigravity configuration.
    subprocess.run(
        [str(python_exe), "-c", "import subagentbridge, mcp"],
        check=True,
    )

    config = load_config(config_path)
    config["mcpServers"]["subagentbridge"] = {
        "command": str(python_exe),
        "args": ["-m", "subagentbridge.server"],
        "env": {
            "SUBAGENTBRIDGE_DB_PATH": str(db_path),
            "SUBAGENTBRIDGE_MAX_RETRIES": "2",
            "SUBAGENTBRIDGE_DEFAULT_TIMEOUT_S": "600",
        },
    }
    atomic_write_json(config_path, config)

    print("SubagentBridge installed and registered globally.")
    print("Refresh MCP servers in Antigravity, then verify with subagentbridge/list_agents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
