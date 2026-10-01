"""Preview or explicitly uninstall StoreClean and restart the target process."""

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADB = "F:/Android/Sdk/platform-tools/adb.exe"


def commands(serial):
    return [
        [ADB, "-s", serial, "uninstall", "io.github.storeclean"],
        [ADB, "-s", serial, "shell", "am", "force-stop", "com.xiaomi.market"],
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial")
    parser.add_argument("--apply", action="store_true", help="Explicitly confirm the displayed uninstall operation")
    args = parser.parse_args()
    if args.apply and not args.serial:
        parser.error("--apply requires an explicit --serial")
    plan = commands(args.serial or "SERIAL")
    print("Target: io.github.storeclean (module only); process restart: com.xiaomi.market")
    for command in plan:
        print(subprocess.list2cmdline(command))
    if not args.apply:
        print("DRY RUN: no device command executed")
        return
    records = []
    for command in plan:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        records.append({"command": command, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        print(result.stdout.strip())
        if result.returncode:
            raise RuntimeError(records[-1])
        if "uninstall" in command and result.stdout.strip() != "Success":
            raise RuntimeError("Uninstall did not report Success")
    directory = ROOT / "release"
    directory.mkdir(exist_ok=True)
    (directory / "rollback-device-verification.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
