"""Record explicit ADB baseline/upgrade checks; no data clearing or uninstall."""

import argparse
import hashlib
import json
import re
import subprocess
import time
import shlex
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from inspect_apks import ROOT


def parse_arguments(argv=None):
    manifest = ET.parse(ROOT / "module/AndroidManifest.xml").getroot()
    version = manifest.get("{http://schemas.android.com/apk/res/android}versionName")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--stage", choices=("before", "upgrade", "after", "settings", "settings-bottom"), required=True)
    parser.add_argument("--apk", default=f"release/storeclean-{version}.apk")
    return parser.parse_args(argv)


def package_paths(output):
    paths = []
    for line in output.splitlines():
        if not line.startswith("package:/") or not line.endswith(".apk"):
            raise ValueError("Unexpected pm path output")
        path = line.removeprefix("package:")
        if not re.fullmatch(r"/[A-Za-z0-9._~+=/-]+\.apk", path):
            raise ValueError("Unexpected characters in APK path")
        paths.append(path)
    if not paths:
        raise ValueError("No APK paths returned")
    return paths


def create_session():
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex
    directory = ROOT / "analysis/device_checks" / name
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def swipe_coordinates(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("Invalid screen dimensions")
    return width // 2, int(height * 0.82), width // 2, int(height * 0.24)


def main():
    args = parse_arguments()
    apk = (ROOT / args.apk).resolve()
    apk.relative_to(ROOT)
    expected = hashlib.sha256(apk.read_bytes()).hexdigest()
    directory = create_session()
    records = []
    completed = False

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
            paths = package_paths(package["stdout"])
            for index, path in enumerate(paths):
                run(["pull", path, str(directory / f"installed-module-before-{index}.apk")])
        if args.stage == "upgrade":
            installed = run(["install", "-r", str(apk)])
            if "Success" not in installed["stdout"].splitlines():
                raise RuntimeError("Install did not report Success")
            run(["shell", "am", "force-stop", "com.xiaomi.market"])
            run(["shell", "am", "start", "-W", "-n", "com.xiaomi.market/.ui.DefaultLauncherIcon"])
            time.sleep(5)
        if args.stage in ("settings", "settings-bottom"):
            run(["shell", "su", "-c", "am start -W -n com.xiaomi.market/"
                 "com.xiaomi.market.business_ui.settings.function.FunctionSettingsFragmentActivity"])
            time.sleep(1)
            if args.stage == "settings-bottom":
                focus = run(["shell", "dumpsys", "window"])
                focus["stdout"] = "\n".join(line for line in focus["stdout"].splitlines() if "mCurrentFocus=" in line)
                focus["output_filter"] = "mCurrentFocus only"
                if "FunctionSettingsFragmentActivity" not in focus["stdout"]:
                    raise RuntimeError("Settings is not foreground; skipping input injection")
                size = run(["shell", "wm", "size"])
                dimensions = re.findall(r"(\d+)x(\d+)", size["stdout"])
                if not dimensions:
                    raise RuntimeError("Screen dimensions unavailable")
                coordinates = swipe_coordinates(*map(int, dimensions[-1]))
                run(["shell", "su", "-c", "input swipe " + " ".join(map(str, coordinates)) + " 450"])
                time.sleep(1)
        for package in ("io.github.storeclean", "com.xiaomi.market"):
            result = run(["shell", "dumpsys", "package", package])
            result["stdout"] = "\n".join(line for line in result["stdout"].splitlines()
                                             if "versionName=" in line or "versionCode=" in line)
            result["output_filter"] = "versionName/versionCode only (includes disabled system package if present)"
        module = run(["shell", "pm", "path", "io.github.storeclean"])
        module_paths = package_paths(module["stdout"])
        if len(module_paths) != 1:
            raise RuntimeError("Expected standalone module APK")
        module_hash = run(["shell", "sha256sum", module_paths[0]])
        if args.stage != "before":
            assert module_hash["stdout"].split()[0] == expected, "Installed APK differs from release"
        paths = run(["shell", "pm", "path", "com.xiaomi.market"])
        for path in package_paths(paths["stdout"]):
            run(["shell", "su", "-c", "sha256sum " + shlex.quote(path)])
        run(["shell", "pidof", "com.xiaomi.market"], required=False)
        listing = run(["shell", "su", "-c", "ls /data/adb/lspd/log"])
        logs = [name for name in listing["stdout"].split() if re.fullmatch(r"modules_[\w:.-]+\.log", name)]
        for name in logs:
            run(["shell", "su", "-c", "grep StoreClean /data/adb/lspd/log/" + name], required=False)
        run(["logcat", "-d", "-b", "crash", "-v", "threadtime"])
        command = ["adb", "-s", args.serial, "exec-out", "screencap", "-p"]
        result = subprocess.run(command, capture_output=True)
        records.append({"command": command, "exit_code": result.returncode,
                        "stderr": result.stderr.decode("utf-8", errors="replace")})
        assert result.returncode == 0 and result.stdout.startswith(b"\x89PNG\r\n\x1a\n")
        screen = directory / (args.stage + "-screen.png")
        screen.write_bytes(result.stdout)
        records.append({"command": command, "exit_code": result.returncode, "stdout_artifact": str(screen),
                        "sha256": hashlib.sha256(result.stdout).hexdigest()})
        completed = True
    finally:
        record = {"stage": args.stage, "time_utc": datetime.now(timezone.utc).isoformat(),
                  "completed": completed, "requested_apk": str(apk), "requested_apk_sha256": expected,
                  "commands": records, "scope": "No app data clearing; visual interpretation recorded separately"}
        (directory / (args.stage + "-commands.json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RECORDED {directory / (args.stage + '-commands.json')}")
    for record in records:
        if "StoreClean]" in record.get("stdout", ""):
            print("\n".join(record["stdout"].splitlines()[-4:]))


if __name__ == "__main__":
    main()
