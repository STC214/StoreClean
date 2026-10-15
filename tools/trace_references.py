"""Locate caller evidence without full third-party decompilation."""

import json
import argparse
import re
import subprocess
import zipfile

from inspect_apks import ROOT


DEXDUMP = "F:/Android/Sdk/build-tools/36.1.0/dexdump.exe"
TARGETS = re.compile(r"OrchardEntranceManager;?\.(?:isOpen|close|reopen)|SettingsUtils;?\.(?:isOrchardEnabled|needBlockWelfare)|pref_key_short_play|pref_key_orchard|orchard_entry|orchard_floating_button|\.launchOrchard|\.handleOrchard")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", help="Limit tracing to one inventory analysis directory")
    args = parser.parse_args()
    entries = json.loads((ROOT / "analysis/inventory.json").read_text(encoding="utf-8"))
    for entry in entries:
        directory = ROOT / entry["analysis_directory"]
        if args.directory and directory.name != args.directory:
            continue
        references = []
        commands = []
        with zipfile.ZipFile(ROOT / entry["copy"]) as archive:
            for dex in entry["dex"]:
                path = directory / dex["name"]
                if not path.exists():
                    path.write_bytes(archive.read(dex["name"]))
                command = [DEXDUMP, "-d", str(path)]
                class_name = method_name = ""
                with (directory / (dex["name"] + ".stderr.txt")).open("w", encoding="utf-8") as errors:
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True, encoding="utf-8", errors="replace")
                    for line in process.stdout:
                        if "Class descriptor" in line:
                            class_name = line.strip()
                        elif re.search(r"\bname\s+: '", line):
                            method_name = line.strip()
                        if TARGETS.search(line) and ("invoke-" in line or "const-string" in line):
                            references.append({"dex": dex["name"], "class": class_name, "method": method_name, "instruction": line.strip()})
                    status = process.wait()
                commands.append({"command": command, "exit_code": status})
                if status:
                    raise RuntimeError(commands[-1])
        (directory / "caller_references.json").write_text(json.dumps(references, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (directory / "trace_commands.json").write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{directory.name}: {len(references)} targeted caller references")


if __name__ == "__main__":
    main()
