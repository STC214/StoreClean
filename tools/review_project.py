"""Repeat offline/static review checks and append exact results; no device modifications."""

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

import build_module
from collect_evidence import JAVA
from inspect_apks import ROOT


def preference_lookup_owner(source):
    match = re.search(r"L([^;\n]+);->findPreference\(Ljava/lang/CharSequence;\)Landroidx/preference/Preference;", source)
    if not match:
        raise ValueError("No observed findPreference owner")
    return match[1].replace("/", ".")


def main():
    records = []
    output = ROOT / "analysis/review_2026-10-15.json"
    successful = False
    artifact_hash = None

    def run(command):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=ROOT, capture_output=True)
        record = {"command": command, "exit_code": result.returncode,
                  "stdout": result.stdout.decode("utf-8", errors="replace"),
                  "stderr": result.stderr.decode("utf-8", errors="replace")}
        records.append(record)
        if result.returncode:
            raise RuntimeError(record)
        return record

    try:
        run([sys.executable, "-X", "utf8", "tools/test_regressions.py", "-v"])
        run([sys.executable, "-X", "utf8", "tools/verify_analysis.py"])
        run([sys.executable, "-X", "utf8", "tools/build_module.py", "--check-inputs"])
        verification_path = build_module.ARTIFACTS / f"storeclean-{build_module.VERSION}-verification.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        artifact_hash = verification["apk_sha256"]
        build_module.require_matching_inputs(verification)
        for key in ("apk", "patch", "source_zip"):
            assert build_module.sha256(ROOT / verification[key]) == verification[key + "_sha256"]
        assert all(record["exit_code"] == 0 for record in verification["commands"])
        for record in verification["commands"]:
            if record["command"][:2] == ["java", "-cp"] and record["command"][3].startswith("io.github.storeclean."):
                run(record["command"])
        run(["java", "-jar", build_module.BUILD_TOOLS / "lib/apksigner.jar", "verify", "--print-certs", verification["apk"]])
        run(["git", "apply", "--check", "--directory=module/build/patch-check", verification["patch"]])
        run([sys.executable, "-X", "utf8", "tools/rollback_module.py"])
        with zipfile.ZipFile(verification["apk"]) as archive:
            assert archive.testzip() is None
            assert len([name for name in archive.namelist() if name.endswith("/ic_launcher.png")]) == 5
        with zipfile.ZipFile(verification["source_zip"]) as archive:
            assert archive.testzip() is None
            assert "icon.png" not in archive.namelist()
            assert not any("/signing/" in name or name.endswith(".jks") for name in archive.namelist())
            for path in build_module.write_patch(ROOT / "module/build/review-source-check.patch"):
                name = path.relative_to(ROOT).as_posix()
                assert archive.read(name) == path.read_bytes(), "Source archive out of date: " + name
        inventory = json.loads((ROOT / "analysis/inventory.json").read_text(encoding="utf-8"))
        for entry in inventory:
            directory = ROOT / entry["analysis_directory"]
            fragment_source = (directory / "FunctionSettingsFragment.smali").read_text(encoding="utf-8")
            owner = preference_lookup_owner(fragment_source)
            target = directory / "PreferenceLookupOwner.smali"
            if not target.exists():
                result = run(JAVA + ["dex", "code", "--class", owner, str(ROOT / entry["copy"])])
                target.write_text(result["stdout"], encoding="utf-8")
            source = target.read_text(encoding="utf-8")
            assert re.search(r"^\.class .*L" + re.escape(owner.replace(".", "/")) + ";", source, re.MULTILINE)
            assert re.search(r"^\.method public(?: [a-z]+)* findPreference\(Ljava/lang/CharSequence;\)Landroidx/preference/Preference;", source, re.MULTILINE)
            assert "getKey()Ljava/lang/String;" in (directory / "Preference.smali").read_text(encoding="utf-8")
            assert "setEnabled(Z)V" in (directory / "Preference.smali").read_text(encoding="utf-8")
        for path in (ROOT / "module/res").rglob("*.xml"):
            ET.parse(path)
        successful = True
    finally:
        history = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"runs": []}
        history["runs"].append({"time_utc": datetime.now(timezone.utc).isoformat(), "passed": successful,
                                "apk_sha256": artifact_hash,
                                "scope": "Offline regression, JVM callbacks/contracts, static APK signatures and artifact integrity; no Android execution",
                                "commands": records})
        output.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS review round {len(history['runs'])}: no new finding in the declared checks")


if __name__ == "__main__":
    main()
