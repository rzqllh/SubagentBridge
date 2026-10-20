#!/usr/bin/env python3
"""bve_tool - cross-platform helper that produces BootstrapVerificationEvidence (BVE).

Standard library only. Works the same on Windows, Linux and macOS.

Subcommands
  utcnow                      print the current UTC time as YYYY-MM-DDTHH:MM:SSZ
  sha256 FILE [FILE ...]      print "<sha256>  <file>" lines (sha256sum format)
  run  --log-dir D --label L [--cwd C] [--timeout S] -- ARGV...
                              run ARGV without a shell, stream its combined
                              stdout+stderr to the console and to a log file
                              in D, then append one JSON record to D/records.jsonl
  selftest                    prove on THIS machine that `run` reports the real
                              exit code, enforces the timeout, keeps logs outside
                              the checkout, and records the correct SHA-256

`run` exit status
  the child's exit status (a signal death maps to 128+signal on POSIX)
  124 on timeout (the record has "timed_out": true)
  125 on misuse (for example the log directory is inside the working directory)
  127 when the executable cannot be found

Limits (be honest about them)
  * BVE records are plain files. They are NOT tamper-evident. A verifier copies the
    values into its report; they are evidence of a verifier-run command, never an
    executor receipt.
  * Child processes are killed on timeout on a best-effort basis (process group on
    POSIX, taskkill /T on Windows).
  * The Windows code path was written without a Windows machine and must be proven
    by running `selftest` there.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

TOOL_VERSION = "1.0.0"


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(cwd, *args):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _is_inside(child, parent):
    child = pathlib.Path(os.path.realpath(child))
    parent = pathlib.Path(os.path.realpath(parent))
    return child == parent or parent in child.parents


def _kill_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def cmd_run(args):
    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        print("bve_tool run: no command given after --", file=sys.stderr)
        return 125
    cwd = os.path.realpath(args.cwd)
    log_dir = os.path.realpath(args.log_dir)
    if _is_inside(log_dir, cwd):
        print("bve_tool run: refusing to write logs inside the checkout (%s)" % cwd, file=sys.stderr)
        return 125
    os.makedirs(log_dir, exist_ok=True)

    bve_id = str(uuid.uuid4())
    safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in args.label)
    log_path = os.path.join(log_dir, "%s-%s.log" % (safe_label, bve_id[:8]))

    resolved = shutil.which(argv[0], path=os.environ.get("PATH"))
    start = utcnow()
    t0 = time.time()
    exit_code = None
    timed_out = False
    error = None

    if resolved is None:
        error = "executable not found: %s" % argv[0]
        open(log_path, "wb").close()
        tool_status = 127
    else:
        popen_kwargs = {"cwd": cwd, "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "shell": False}
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen([resolved] + argv[1:], **popen_kwargs)
        timer = None
        flag = {"hit": False}
        if args.timeout and args.timeout > 0:
            def _expire():
                flag["hit"] = True
                _kill_tree(proc)
            timer = threading.Timer(args.timeout, _expire)
            timer.daemon = True
            timer.start()
        with open(log_path, "wb") as log:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                log.write(chunk)
                try:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                except Exception:
                    pass
        exit_code = proc.wait()
        if timer:
            timer.cancel()
        timed_out = flag["hit"]
        if timed_out:
            tool_status = 124
        elif exit_code < 0:
            tool_status = 128 + (-exit_code)
        else:
            tool_status = exit_code

    end = utcnow()
    record = {
        "bve_id": bve_id,
        "tool_version": TOOL_VERSION,
        "tool_sha256": sha256_file(os.path.abspath(__file__)),
        "label": args.label,
        "argv": argv,
        "resolved_executable": resolved,
        "cwd": cwd,
        "start_utc": start,
        "end_utc": end,
        "duration_s": round(time.time() - t0, 3),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "error": error,
        "log_path": log_path,
        "log_sha256": sha256_file(log_path),
        "log_bytes": os.path.getsize(log_path),
        "git_head": _git(cwd, "rev-parse", "HEAD"),
        "git_tree": _git(cwd, "rev-parse", "HEAD^{tree}"),
        "git_dirty": bool(_git(cwd, "status", "--porcelain")),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    with open(os.path.join(log_dir, "records.jsonl"), "a", encoding="utf-8") as rec:
        rec.write(json.dumps(record) + "\n")
    print(
        "\nBVE %s label=%s exit_code=%s timed_out=%s log_sha256=%s"
        % (bve_id, args.label, exit_code, timed_out, record["log_sha256"]),
        file=sys.stderr,
    )
    return tool_status


def cmd_sha256(args):
    status = 0
    for f in args.files:
        try:
            print("%s  %s" % (sha256_file(f), f))
        except OSError as e:
            print("bve_tool sha256: %s: %s" % (f, e), file=sys.stderr)
            status = 1
    return status


def cmd_selftest(_args):
    here = os.path.abspath(__file__)
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", name, (" - " + detail) if detail else ""))

    def run_tool(logs, cwd, label, extra, child):
        cmd = [sys.executable, here, "run", "--log-dir", logs, "--cwd", cwd, "--label", label] + extra + ["--"] + child
        return subprocess.run(cmd, capture_output=True, text=True)

    def last_record(logs):
        with open(os.path.join(logs, "records.jsonl"), encoding="utf-8") as f:
            return json.loads(f.read().strip().splitlines()[-1])

    with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as logs:
        cwd = os.path.join(work, "checkout")
        os.makedirs(cwd)
        py = sys.executable

        r = run_tool(logs, cwd, "ok", [], [py, "-c", "print('SELFTEST-MARKER')"])
        rec = last_record(logs)
        check("exit code 0 is reported as 0", r.returncode == 0 and rec["exit_code"] == 0, "tool=%s rec=%s" % (r.returncode, rec["exit_code"]))
        check("child output reaches the console and the log", "SELFTEST-MARKER" in r.stdout and os.path.getsize(rec["log_path"]) > 0)
        check("recorded log SHA-256 equals an independent hash", rec["log_sha256"] == sha256_file(rec["log_path"]))
        check("log lives outside the checkout", not _is_inside(rec["log_path"], cwd))

        r = run_tool(logs, cwd, "fail3", [], [py, "-c", "import sys; sys.exit(3)"])
        rec = last_record(logs)
        check("exit code 3 is reported as 3 (not masked)", r.returncode == 3 and rec["exit_code"] == 3, "tool=%s rec=%s" % (r.returncode, rec["exit_code"]))

        r = run_tool(logs, cwd, "timeout", ["--timeout", "1"], [py, "-c", "import time; time.sleep(30)"])
        rec = last_record(logs)
        check("timeout is enforced and flagged", r.returncode == 124 and rec["timed_out"] is True and rec["duration_s"] < 20, "tool=%s duration=%ss" % (r.returncode, rec["duration_s"]))

        r = run_tool(cwd, cwd, "inside", [], [py, "-c", "pass"])
        check("log directory inside the checkout is refused", r.returncode == 125, "tool=%s" % r.returncode)

        r = run_tool(logs, cwd, "missing", [], ["definitely-not-a-real-executable-xyz"])
        rec = last_record(logs)
        check("missing executable is reported, not silently passed", r.returncode == 127 and rec["error"] is not None, "tool=%s" % r.returncode)

    ok = all(results)
    print("\nSELFTEST %s (%d/%d) on %s, python %s" % ("PASSED" if ok else "FAILED", sum(results), len(results), platform.platform(), platform.python_version()))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(prog="bve_tool", description="BootstrapVerificationEvidence helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("utcnow")
    s = sub.add_parser("sha256")
    s.add_argument("files", nargs="+")
    r = sub.add_parser("run")
    r.add_argument("--log-dir", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--cwd", default=".")
    r.add_argument("--timeout", type=float, default=0)
    r.add_argument("argv", nargs=argparse.REMAINDER)
    sub.add_parser("selftest")
    args = p.parse_args()
    if args.cmd == "utcnow":
        print(utcnow())
        return 0
    if args.cmd == "sha256":
        return cmd_sha256(args)
    if args.cmd == "run":
        return cmd_run(args)
    return cmd_selftest(args)


if __name__ == "__main__":
    sys.exit(main())
