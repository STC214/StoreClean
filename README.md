# StoreClean

StoreClean 是一个面向 Android 应用商店的 LSPosed 模块。项目目标、受控设置及详细验收条件见 [`CORE_REQUIREMENTS.md`](CORE_REQUIREMENTS.md)；APK 静态分析与运行记录见 [`analysis/REPORT.md`](analysis/REPORT.md) 和 [`analysis/RUNTIME_VALIDATION.md`](analysis/RUNTIME_VALIDATION.md)。

当前正式版 **1.1.1**：新增本地裁剪的头像图标，固定开关策略及入口拦截目标保持不变；重复审查后补强方法与类结构校验、构建完整性和证据管理。模块屏蔽小米应用商店左侧水果活动入口，固定 15 个功能设置开关；安全检测开关保持原逻辑。已登记 4.126.10、4.126.s.1、4.126.s.2、4.127.11；未登记 4.x 版本只在完整结构检查通过后尝试启用。2026-10-15，1.1.0 已在 4.127.11 上确认入口消失、开关正常；见 [`analysis/COMPATIBILITY_1.1.0.md`](analysis/COMPATIBILITY_1.1.0.md)。1.1.1 尚未安装到手机；最新审查范围见 [`analysis/REVIEW_2026-10-15.md`](analysis/REVIEW_2026-10-15.md)。

## 项目结构

- `module/`：模块源码、Android 清单、资源、fixture 与 JVM 测试；模块使用说明见 [`module/README.md`](module/README.md)。
- `tools/`：APK 分析、证据校验、构建和回退脚本。
- `analysis/`：版本比较、分析报告及验证记录。
- `store_apk/`：用于分析的 APK 输入，保留在本地。
- `release/`：仅存放最新发行 APK。
- `analysis/release_artifacts/`：源码归档、补丁、签名旁文件和构建验证记录，保留在本地。

## 环境要求

- Python 3
- JDK（`javac`、`java`、`jar`）
- Android SDK；构建脚本当前指向 `F:/Android/Sdk`，使用 Android 35 平台和 Build Tools 36.1.0
- 构建正式升级包需存在项目现有签名材料 `module/signing/storeclean-dev.jks`。密钥不纳入版本库。

## 分析与验证

在项目根目录运行：

```text
python -X utf8 tools/verify_analysis.py
```

该命令复核分析脚本、APK 副本哈希、签名及已采集类的一致性，并更新 `analysis/verification_commands.json`。详细命令与结果保存在 `analysis/` 下的 JSON 记录中。

## 构建

先检查输入及本机构建条件，再构建发行包：

```text
python -X utf8 tools/build_module.py --check-inputs
python -X utf8 tools/build_module.py
```

构建 APK 写入 `release/`，源码 ZIP、补丁、`.idsig` 和验证 JSON 写入 `analysis/release_artifacts/`，中间产物写入 `module/build/`。构建脚本会运行 JVM/fixture 测试并验证产物。发行和设备验收的具体步骤见 [`module/README.md`](module/README.md)。

## 回退

常规回退是在 LSPosed 中停用模块并重启目标应用进程。设备回退脚本默认仅预览：

```text
python -X utf8 tools/rollback_module.py
```

确认目标设备后，按 `module/README.md` 的说明显式传入设备序列号和 `--apply`。脚本回退会卸载本模块并结束目标应用进程，不会卸载目标应用或清除其数据。

## 本地文件与临时产物

原始 APK、发行产物、提取分析目录、构建目录、依赖缓存和签名材料按 `.gitignore` 规则留在本地或排除于版本控制。临时分析下载文件及 Python 缓存不属于项目文档或源码。

`release/` 只保留最新 APK，其他发行资料归档到 `analysis/release_artifacts/`，不删除历史资料。旧 APK 清理使用 `tools/clean_release.ps1` 先预览绝对路径，确认后加 `-Apply` 执行；整理旧布局可用 `tools/organize_release.ps1` 先预览、确认后移动文件。操作不涉及 `store_apk/` 样本。原始 `icon.png` 留在本地，裁剪后的图标资源可纳入版本库。
