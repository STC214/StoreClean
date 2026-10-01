"""Compare settings schemas and hook candidates, and verify read-only evidence."""

import hashlib
import json
import re

from inspect_apks import ROOT


GETTERS = {
    "isH5TopicEnabled": False,
    "isGlobalNetEnabled": False,
    "isQuickAppEnabled": False,
    "needAutoAddCloudGameIcon": False,
    "needAutoAddCloudGameIconForCloud": False,
    "supportGameLottery": False,
    "isQuickAppGameEnabled": False,
    "isMiniProgramRevisitEnabled": False,
    "needBlockWelfare": True,
    "isChildModeSettingCheck": False,
    "isOrchardEnabled": False,
    "needPhoneClean": True,
    "isAppLockCheck": True,
    "isPermissionManagementCheck": True,
    "isMilinkServiceCheck": True,
}


def schema(directory):
    resources = (directory / "resources.txt").read_text(encoding="utf-8")
    resources = "\n".join(block for block in re.split(r"^      config ", resources, flags=re.MULTILINE)[1:] if block.startswith("zh-rCN:"))
    titles = {}
    for match in re.finditer(r'resource (0x[0-9a-f]+) com\.xiaomi\.market:string/([^:]+):[^\n]*\n\s+\(string8\) "([^\n]*)"', resources):
        if re.search(r"[\u4e00-\u9fff]", match[3]):
            titles.setdefault(match[1], {"name": match[2], "text": match[3]})
    category = None
    item = None
    entries = []
    for line in (directory / "function_settings.xmltree.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("    E: PreferenceCategory"):
            category = None
            item = None
        elif line.startswith("      A: android:title"):
            category = titles[line.split("=@")[1]]["text"]
        elif line.startswith("      E: CheckBoxPreference"):
            item = {"category": category}
            entries.append(item)
        elif item is not None and line.startswith("        A: android:title"):
            item["title"] = titles[line.split("=@")[1]]["text"]
        elif item is not None and line.startswith("        A: android:key"):
            item["key"] = re.search(r'="([^"]+)"', line)[1]
            item["required"] = None if item["key"] == "pref_key_app_security_check" else item["category"] == "我的页功能管理"
    return entries


def main():
    inventory = json.loads((ROOT / "analysis/inventory.json").read_text(encoding="utf-8"))
    summaries = []
    checks = []
    for entry in inventory:
        directory = ROOT / entry["analysis_directory"]
        with (ROOT / entry["file"]).open("rb") as source:
            assert hashlib.file_digest(source, "sha256").hexdigest() == entry["sha256"]
        with (ROOT / entry["copy"]).open("rb") as source:
            assert hashlib.file_digest(source, "sha256").hexdigest() == entry["sha256"]
        badging = (directory / "badging.txt").read_text(encoding="utf-8").splitlines()[0]
        name = re.search(r"versionName='([^']+)'", badging)[1]
        code = int(re.search(r"versionCode='([^']+)'", badging)[1])
        settings = schema(directory)
        assert len(settings) == 16
        utils = (directory / "SettingsUtils.smali").read_text(encoding="utf-8")
        hooks = {}
        for method, result in GETTERS.items():
            match = re.search(r"^\.method public static " + method + r"\(\)Z\n.*?^\.end method", utils, re.MULTILINE | re.DOTALL)
            assert match, f"Missing getter: {method} ({name})"
            hooks[method] = {"required_return": result, "strings": re.findall(r'const-string(?:/jumbo)? \w+, "([^"]*)"', match[0])}
        orchard = (directory / "OrchardEntranceManager.smali").read_text(encoding="utf-8")
        assert ".method public static final isOpen()Z" in orchard
        assert "isSupportAppSecurityCheck" not in GETTERS
        checks.append({"version": name, "original_and_copy_hash": "PASS", "settings_count": 16, "getters_present": len(hooks), "security_check_excluded": "PASS"})
        summaries.append({"version": name, "version_code": code, "sha256": entry["sha256"], "directory": entry["analysis_directory"], "settings": settings, "getter_candidates": hooks})
        print(f"{name} ({code}): original/copy SHA-256 PASS; 16 settings; {len(hooks)} getter candidates PASS")
    key_schemas = [[(item["category"], item["key"], item["required"]) for item in value["settings"]] for value in summaries]
    schemas_equal = all(value == key_schemas[0] for value in key_schemas)
    assert schemas_equal
    (ROOT / "analysis/comparison.json").write_text(json.dumps({"schemas_equal": schemas_equal, "versions": summaries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "analysis/verification.json").write_text(json.dumps({"command": "python -X utf8 tools/compare_apks.py", "checks": checks, "schemas_equal": schemas_equal, "scope": "static analysis only; device runtime not tested"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for setting in summaries[0]["settings"]:
        print(json.dumps(setting, ensure_ascii=False))


if __name__ == "__main__":
    main()
