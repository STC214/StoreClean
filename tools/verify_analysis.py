"""Record literal verification outputs and signature checks for collected APKs."""

import hashlib
import json
import subprocess
import sys

from inspect_apks import ROOT


def run(command):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    record = {"command": command, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    assert result.returncode == 0, record
    return record


def main():
    for path in (ROOT / "tools").glob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    records = [run([sys.executable, "-X", "utf8", "tools/compare_apks.py"])]
    inventory = json.loads((ROOT / "analysis/inventory.json").read_text(encoding="utf-8"))
    class_hashes = {}
    for entry in inventory:
        directory = ROOT / entry["analysis_directory"]
        records.append(run(["java", "-jar", "F:/Android/Sdk/build-tools/36.1.0/lib/apksigner.jar", "verify", "--print-certs", str(ROOT / entry["copy"])]))
        class_hashes[directory.name] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.glob("*.smali")}
        for filename in ("evidence_commands.json", "trace_commands.json"):
            commands = json.loads((directory / filename).read_text(encoding="utf-8"))
            assert all(command["exit_code"] == 0 for command in commands)
        assert len(class_hashes[directory.name]) >= 12
    assert class_hashes["apk_2"] == class_hashes["apk_3"]
    verification = {"records": records, "collected_class_sha256": class_hashes, "s1_s2_collected_classes_identical": True, "device_runtime": "NOT TESTED", "module_build": "See module build verification record"}
    (ROOT / "analysis/verification_commands.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    count = len(class_hashes["apk_2"])
    print(f"PASS: scripts parse; original/copy hashes match; 16 settings per version; 15 getter candidates per version; signatures valid; {count} collected classes identical between s.1 and s.2")


if __name__ == "__main__":
    main()
