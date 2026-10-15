"""Record explicit ADB baseline/upgrade checks; no data clearing or uninstall."""

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone

from inspect_apks import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--stage", choices=("before", "upgrade", "after", "settings", "settings-bottom"), required=True)
    parser.add_argument("--apk", default="release/storeclean-1.1.0.apk")
    args = parser.parse_args()
    directory = ROOT / "analysis/device_1.1.0"
    directory.mkdir(parents=True, exist_ok=True)
    records = []

    def run(arguments, required=True):
        command = ["adb", "-s", args.serial] + arguments
        result = subprocess.run(command, capture_output=True)
        record = {"command": command, "exit_code": result.returncode,
                  "stdout": result.stdout.decode("utf-8", errors="replace"),
                  "stderr": result.stderr.decode("utf-8", errors="replace")}
        records.append(record)
        if required and result.returncode:
            raise RuntimeError(record)
        return record

    try:
        if args.stage == "before":
            package = run(["shell", "pm", "path", "io.github.storeclean"])
            path = package["stdout"].strip().removeprefix("package:")
            run(["pull", path, str(directory / "installed-module-before.apk")])
        if args.stage == "upgrade":
            apk = (ROOT / args.apk).resolve()
            apk.relative_to(ROOT)
            run(["install", "-r", str(apk)])
            run(["shell", "am", "force-stop", "com.xiaomi.market"])
            run(["shell", "am", "start", "-W", "-n", "com.xiaomi.market/.ui.DefaultLauncherIcon"])
            time.sleep(5)
        if args.stage in ("settings", "settings-bottom"):
            run(["shell", "su", "-c", "am start -W -n com.xiaomi.market/"
                 "com.xiaomi.market.business_ui.settings.function.FunctionSettingsFragmentActivity"])
            time.sleep(1)
            if args.stage == "settings-bottom":
                run(["shell", "su", "-c", "input swipe 580 2050 580 600 450"])
                time.sleep(1)
        for package in ("io.github.storeclean", "com.xiaomi.market"):
            result = run(["shell", "dumpsys", "package", package])
            result["stdout"] = "\n".join(line for line in result["stdout"].splitlines()
                                             if "versionName=" in line or "versionCode=" in line)
            result["output_filter"] = "versionName/versionCode only (includes disabled system package if present)"
        module = run(["shell", "pm", "path", "io.github.storeclean"])
        module_path = module["stdout"].strip().removeprefix("package:")
        module_hash = run(["shell", "sha256sum", module_path])
        if args.stage != "before":
            expected = hashlib.sha256((ROOT / args.apk).read_bytes()).hexdigest()
            assert module_hash["stdout"].split()[0] == expected, "Installed APK differs from release"
        paths = run(["shell", "pm", "path", "com.xiaomi.market"])
        path = paths["stdout"].strip().removeprefix("package:")
        run(["shell", "su", "-c", "sha256sum " + path])
        run(["shell", "pidof", "com.xiaomi.market"], required=False)
        listing = run(["shell", "su", "-c", "ls /data/adb/lspd/log"])
        logs = [name for name in listing["stdout"].split() if re.fullmatch(r"modules_[\w:.-]+\.log", name)]
        for name in logs:
            run(["shell", "su", "-c", "grep StoreClean /data/adb/lspd/log/" + name], required=False)
        run(["logcat", "-d", "-b", "crash", "-v", "threadtime"])
        command = ["adb", "-s", args.serial, "exec-out", "screencap", "-p"]
        result = subprocess.run(command, capture_output=True)
        assert result.returncode == 0 and result.stdout.startswith(b"\x89PNG\r\n\x1a\n")
        screen = directory / (args.stage + "-screen.png")
        screen.write_bytes(result.stdout)
        records.append({"command": command, "exit_code": result.returncode, "stdout_artifact": str(screen),
                        "sha256": hashlib.sha256(result.stdout).hexdigest()})
    finally:
        record = {"stage": args.stage, "time_utc": datetime.now(timezone.utc).isoformat(),
                  "commands": records, "scope": "No app data clearing; visual interpretation recorded separately"}
        (directory / (args.stage + "-commands.json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RECORDED {directory / (args.stage + '-commands.json')}")
    for record in records:
        if "StoreClean]" in record.get("stdout", ""):
            print("\n".join(record["stdout"].splitlines()[-4:]))


if __name__ == "__main__":
    main()
