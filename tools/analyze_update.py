"""Append an APK sample without reindexing historical evidence; compare hook classes."""

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

from collect_evidence import CLASSES, JAVA
from compare_apks import schema
from inspect_apks import AAPT, ROOT, capture, dex_strings


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_evidence_destination(directory):
    directory = directory.resolve()
    base = (ROOT / "analysis").resolve()
    directory.relative_to(base)
    if directory == base:
        raise ValueError("Use a dedicated analysis subdirectory")
    if directory.exists() and any(directory.iterdir()) and not (directory / "input.apk").is_file():
        raise ValueError("Nonempty evidence directory has no bound input.apk")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    apk = args.apk.resolve()
    directory = args.directory.resolve()
    apk.relative_to(ROOT)
    directory.relative_to(ROOT)
    validate_evidence_destination(directory)
    inventory_path = ROOT / "analysis/inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    original = digest(apk)
    directory.mkdir(parents=True, exist_ok=True)
    copy = directory / "input.apk"
    if copy.exists():
        assert digest(copy) == original, "Existing evidence belongs to another APK"
    else:
        shutil.copyfile(apk, copy)
    command_file = directory / "evidence_commands.json"
    commands = json.loads(command_file.read_text(encoding="utf-8")) if command_file.exists() else []

    def collect(command, name):
        destination = directory / name
        if not destination.exists() or destination.stat().st_size == 0:
            commands.append(capture(command, destination))
            command_file.write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    collect([AAPT, "dump", "badging", copy], "badging.txt")
    collect([AAPT, "dump", "--values", "resources", copy], "resources.txt")
    collect([AAPT, "dump", "xmltree", copy, "AndroidManifest.xml"], "manifest.txt")
    collect(["java", "-jar", AAPT.parent / "lib/apksigner.jar", "verify", "--verbose", "--print-certs", copy], "signature.txt")
    for name in CLASSES:
        collect(JAVA + ["dex", "code", "--class", name, str(copy)], name.rsplit(".", 1)[1] + ".smali")
    resources = (directory / "resources.txt").read_text(encoding="utf-8")
    for kind, name in (("xml", "function_settings"), ("layout", "main_search_container"),
                       ("layout", "native_main_search_box_layout")):
        match = re.search(r"resource 0x[0-9a-f]+ com\.xiaomi\.market:" + kind + "/" + name
                          + r':.*?\n\s+\(string8\) "([^"]+)"', resources)
        assert match, "Missing resource: " + name
        collect([AAPT, "dump", "xmltree", copy, match[1]], name + ".xmltree.txt")
    settings = schema(directory)
    baseline = ROOT / inventory[0]["analysis_directory"]
    old_settings = schema(baseline)
    assert [(s["category"], s["key"], s["required"]) for s in settings] == [
        (s["category"], s["key"], s["required"]) for s in old_settings
    ], "Menu schema changed; revise the policy before registering this sample"
    dex = []
    with zipfile.ZipFile(copy) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            if re.fullmatch(r"classes\d*\.dex", name):
                data = archive.read(name)
                dex.append({"name": name, "sha256": hashlib.sha256(data).hexdigest(),
                            "strings": sum(1 for _ in dex_strings(data))})
    differences = []
    for name in CLASSES:
        artifact = name.rsplit(".", 1)[1] + ".smali"
        old = (baseline / artifact).read_text(encoding="utf-8")
        new = (directory / artifact).read_text(encoding="utf-8")
        method_pattern = r"^\.method (.+)$"
        old_methods = set(re.findall(method_pattern, old, re.MULTILINE))
        new_methods = set(re.findall(method_pattern, new, re.MULTILINE))
        differences.append({"class": name, "identical_smali": old == new,
                            "added_methods": sorted(new_methods - old_methods),
                            "removed_methods": sorted(old_methods - new_methods)})
    assert digest(apk) == digest(copy) == original
    entry = {"file": str(apk.relative_to(ROOT)), "analysis_directory": str(directory.relative_to(ROOT)),
             "copy": str(copy.relative_to(ROOT)), "bytes": apk.stat().st_size, "sha256": original,
             "unchanged": True, "zip_integrity": "passed", "dex": dex, "commands": commands}
    matches = [item for item in inventory if item["sha256"] == original]
    if matches:
        assert matches[0]["analysis_directory"] == entry["analysis_directory"]
    else:
        inventory.append(entry)
        inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"apk_sha256": original, "directory": entry["analysis_directory"],
              "baseline_directory": str(baseline.relative_to(ROOT)), "schemas_equal": True,
              "settings": settings, "classes": differences, "scope": "static evidence; not runtime verification"}
    (ROOT / "analysis/update_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "update_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: sample appended, originals unchanged, settings schema matches; class differences recorded")


if __name__ == "__main__":
    main()
