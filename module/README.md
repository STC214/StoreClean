# StoreClean 1.0.0 正式版

LSP / LSPosed 模块，包名 `io.github.storeclean`，作用域仅为小米应用商店 `com.xiaomi.market`。

## 支持版本

| versionName | versionCode |
| --- | --- |
| 4.126.10 | 40007640 |
| 4.126.s.1 | 40007621 |
| 4.126.s.2 | 40007622 |

版本名与版本号必须同时匹配。其他版本只记录提示，不启用目标 hook。

## 当前实现

- 隐藏搜索栏左侧活动 `EntranceView`，跳过活动配置/动画绑定并去除该 View 的点击入口；不隐藏搜索框、设置按钮或整个导航容器。
- 阻断果树 SDK 的五个 `launchOrchard` 重载，并关闭独立果园入口状态。
- 导航栏管理、游戏服务管理、其他功能管理共 11 个开关保持关闭。
- 我的页功能管理的手机清理、应用锁、权限管理、互联升级四个开关保持开启。
- “开启应用安全检测”与其他无关设置按原逻辑处理；未额外强制关闭安全检测。
- 受控开关在功能设置页呈禁用状态，防止反向切换。
- 对受控偏好采用运行时读取覆盖和写入拦截，未直接编辑应用商店 APK、偏好文件或数据库。

共 34 个必需 hook。初始化先解析全部目标，遇到缺失目标时放弃启用；若注册中途失败则尝试撤销本模块已注册的目标 hook，并输出错误。

## 安装与真机验收

1. 安装 `release/storeclean-1.0.0.apk`；已安装 0.1.0 时可直接覆盖更新。
2. 在 LSPosed 管理器启用 **StoreClean 应用商店精简**，作用域仅勾选 **应用商店**。
3. 结束应用商店进程后重新打开，使新版本 Hook 生效；必要时重启设备。
4. 检查 LSPosed 日志中 `[StoreClean] active version=... hooks=34`；出现 `unsupported version` 或 `initialization aborted` 时，保留日志供定位。
5. 检查左侧活动图标不显示，活动跳转被阻断，全部菜单开关符合项目需求；分别在三个版本验证。
6. 检查搜索、下载、安装、更新正常，安全检测保持原行为。

正式版 versionCode 为 2，显式设置 `debuggable=false`，无启动器图标和配置界面。为支持直接覆盖更新，沿用 0.1.0 的现有项目签名（密钥文件名和证书开发标识保留，不伪称为新签名）；请妥善保管密钥，本发行包适用于本项目现有部署，不表示已完成公开分发的密钥治理。

2026-10-01，0.1.0 在应用商店 4.126.10 上已获用户确认：活动图标视觉正常屏蔽，受控开关开闭正确且不可操作；主进程日志确认 34 个 Hook 注册成功，所检查日志未见模块初始化错误，崩溃缓冲区为空。详见 `analysis/RUNTIME_VALIDATION.md`。

1.0.0 保持 Hook 源码不变；构建记录检查其 DEX 与旧包一致、签名证书一致。**1.0.0 覆盖安装后的真机复验尚待进行**；s.1/s.2、深链阻断、搜索/下载/安装/更新、安全检测及设备回退仍需专项实测。初始化日志并非逐项业务验收。

## 回退

普通回退：在 LSPosed 禁用本模块，结束应用商店进程后重新打开；当前进程中的 hook 不会仅因为开关被关闭而立即消失。

脚本回退预览（不执行设备操作）：

```text
python -X utf8 tools/rollback_module.py
```

确认卸载模块并重启应用商店进程后，指定设备执行：

```text
python -X utf8 tools/rollback_module.py --serial SERIAL --apply
```

将 `SERIAL` 换为实际设备序列号。脚本只卸载 `io.github.storeclean` 并结束 `com.xiaomi.market` 进程，不卸载应用商店、不清除其数据。设备回退结果另存为 `release/rollback-device-verification.json`。

回退脚本目前仅验证了预览路径；运行时回退效果仍待真机验证。

## 构建与证据

使用本机 JDK 与 Android SDK，不依赖 Gradle。构建脚本使用固定 SHA-256 校验的 Xposed API 82，仅作编译依赖，不打入 APK。

```text
python -X utf8 tools/build_module.py --check-inputs
python -X utf8 tools/build_module.py
```

当前构建脚本中的 SDK 路径为 `F:/Android/Sdk`。编译依赖下载地址为 `https://api.xposed.info/de/robv/android/xposed/api/82/api-82.jar`，保存到 `module/deps/xposed-api-82.jar`；预期哈希已固定在脚本中。签名文件保留在 `module/signing/`，不进入源代码 ZIP。构建要求已有密钥存在，缺失时停止，不自动生成新证书破坏覆盖更新兼容性。

输出：APK、新增源码 patch、源码 ZIP、逐命令验证 JSON。策略 fixture 验证了基线值、启用覆盖、排除项、存储不变与恢复基线；生产代码回调还通过了明确使用 host fake 的调用测试，覆盖受控读取/写入、排除项放行及入口隐藏/点击清除。它们不运行 Android 页面或真正的 Xposed 引擎，fake 类不进入 APK。

发行产物为 `release/storeclean-1.0.0.apk`、`release/storeclean-1.0.0.patch`、`release/storeclean-1.0.0-source.zip` 和 `release/storeclean-1.0.0-verification.json`。0.1.0 发行文件及版本构建目录已清理；历史真机记录与 1.0.0 验证 JSON 中已完成的基线比较结果保留。后续构建若无旧 APK，将如实标记基线缺失，不重新声称执行了比较。

源码 ZIP 导出模块代码、测试、全部工具脚本及项目说明；复构建仍需本项目的 `analysis/` 证据、`store_apk/` 原件及本机 SDK/编译依赖与签名密钥。`.gitignore` 排除 APK 原件、发行包、提取证据、构建目录、依赖、密钥和缓存，保留源码与分析汇总。

hook 跳过原方法的 API 语义参考：[XposedBridge 官方文档](https://api.xposed.info/reference/de/robv/android/xposed/XposedBridge.html)。本项目 APK 证据见 `analysis/REPORT.md`。
