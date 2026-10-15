# 应用商店模块：版本分析与兼容方案

首轮日期：2026-10-01；兼容性更新：2026-10-15。依据：项目规则、核心需求和 `store_apk/` 中的样本。第 8 节保留 1.0.0 发行历史，1.1.0 兼容性见第 9 节，最新 1.1.1 审查见第 10 节。

## 1. 当前结论

**优先采用 LSP / LSPosed 模块，作用域限制为 `com.xiaomi.market`。**

这是基于本次 APK 实现的方案判断：目标开关集中在 Java/Kotlin 方法、偏好设置与页面状态中，运行时 hook 可以同时控制实际读取结果、菜单显示状态和活动跳转，不必修改或重新签名原 APK。

SukiSU 路线保留为部署或配合注入框架的候选；仅定时修改偏好数据文件，尚不足以证明能覆盖缓存、云控配置、页面状态及独立活动跳转。当前不将其视为与 LSP 等价的已验证方案。

首轮完成静态分析和方案评估；0.1.0 已在应用商店 4.126.10 上获得用户视觉确认和主进程初始化日志。当前 **StoreClean 1.1.0** 已在 4.127.11 上覆盖安装并验证入口与菜单视觉状态；历史记录见 `RUNTIME_VALIDATION.md`，最新证据见 `COMPATIBILITY_1.1.0.md`，不将已测版本扩大为全部版本实测。

## 2. 样本登记

| 分析目录 | APK 文件 | versionName | versionCode |
| --- | --- | --- | --- |
| `apk_1/` | `应用商店_4.126.10.apk` | 4.126.10 | 40007640 |
| `apk_2/` | `应用商店_4.126.s.1.apk` | 4.126.s.1 | 40007621 |
| `apk_3/` | `应用商店_4.126.s.2.apk` | 4.126.s.2 | 40007622 |
| `apk_4/` | `device_4.127.11/com.xiaomi.market/base.apk` | 4.127.11 | 40007661 |

- 包名均为 `com.xiaomi.market`，minSdk 为 24，targetSdk 为 35。
- 每个 APK 均包含五个 DEX，ZIP 完整性检查通过，签名验证通过。
- 三个样本签名证书 SHA-256 相同：`c9009d01ebf9f5d0302bc71b2fe9aa9a47a432bba17308a3111b75d7b2149025`。这一结果仅证明样本签名一致，不单独证明文件来源。
- 原件与英文文件名分析副本 SHA-256 一致，分析后原件哈希保持不变。
- 完整文件 SHA-256、命令与输出路径见 `inventory.json`。

## 3. 功能设置：已定位的完整开关表

四个版本的 `function_settings` XML 分组、key 和目标状态一致，共 16 项：11 项关闭、4 项开启、1 项排除。

| 分组 | 中文标题（zh-rCN 资源） | key | 模块目标状态 |
| --- | --- | --- | --- |
| 导航栏管理 | 视频专区 | `pref_key_short_play` | 关闭 |
| 导航栏管理 | 活动专题页 | `pref_key_h5_topic` | 关闭 |
| 导航栏管理 | 软件-全球上网 | `pref_key_global_net` | 关闭 |
| 导航栏管理 | 软件-快应用 | `pref_key_quick_app` | 关闭 |
| 游戏服务管理 | 自动生成云游戏桌面图标 | `pref_key_cloud_game_icon` | 关闭 |
| 游戏服务管理 | 显示游戏抽奖 | `pref_key_support_game_lottery` | 关闭 |
| 游戏服务管理 | 小游戏服务 | `pref_key_mini_game` | 关闭 |
| 游戏服务管理 | 显示首页最近使用的小程序 | `pref_key_mini_program_switch` | 关闭 |
| 我的页功能管理 | 手机清理功能 | `pref_key_phone_clean` | 开启 |
| 我的页功能管理 | 开启应用安全检测 | `pref_key_app_security_check` | 排除，不强制改变 |
| 我的页功能管理 | 应用锁 | `pref_key_app_lock` | 开启 |
| 我的页功能管理 | 权限管理 | `pref_key_permission_management` | 开启 |
| 我的页功能管理 | 互联升级 | `pref_key_milink_service` | 开启 |
| 其他功能管理 | 显示福利活动 | `pref_key_need_welfare` | 关闭 |
| 其他功能管理 | 未成年人模式 | `pref_key_child_mode_setting` | 关闭 |
| 其他功能管理 | 果园入口 | `pref_key_orchard` | 关闭 |

“开启应用安全检测”按现有需求仅排除在强制开启规则之外，不擅自推导为强制关闭。

## 4. 已确认的实现位置与注意点

### 4.1 菜单与实际生效路径

- 菜单类：`com.xiaomi.market.business_ui.settings.function.FunctionSettingsFragment`。
- 修改分发类：`com.xiaomi.market.business_ui.settings.PreferenceHelperKt`，包含 `onPreferenceKeyChange` 等处理。
- 偏好读取：`com.xiaomi.market.util.PrefUtils.getBoolean(String, boolean, PrefFile[])`。
- 功能状态类：`com.xiaomi.market.util.SettingsUtils`，三个版本均存在 15 个已检查的布尔 getter 候选，详见 `comparison.json`。
- 部分 getter 含静态缓存和 Robust `PatchProxy` 热修复分支；只写偏好文件或只改界面勾选值可能被其他路径覆盖。
- `needBlockWelfare()` 返回的是“屏蔽福利”的状态：目标应返回 `true`，而对应 `pref_key_need_welfare` 应读为 `false`，两者不可混同。
- 视频专区 key 为 `pref_key_short_play`；调用引用涉及 `PageConfig.initTabs`、`PreferenceHelperKt.refreshTabs` 与短剧初始化管理，不能把 `PageConfig.useShortplayTab()` 的页面能力判断等同于用户开关值。
- 各版本资源 ID 有变化，模块应按 key、类名及方法签名定位，避免硬编码跨版本资源数值。

### 4.2 果树入口并非单一路径

- 入口管理类：`com.xiaomi.market.util.OrchardEntranceManager`，提供 `isOpen()`、`close()`、`reopen()`。
- SDK 启动类：`com.xiaomi.market.incentive.orchard.OrchardSdkHelper`，提供多个 `launchOrchard(...)` 重载。
- 调用引用还涉及 `JoinActivity.handleOrchard`、我的页更新视图和更新列表引导。
- 在 4.126.10 的菜单创建方法中，`pref_key_orchard` 对应项被设为不可见；存在内部 key 不等于用户能在菜单里直接关闭该入口。
- 后续已静态定位搜索栏左侧的 `com.xiaomi.market.ui.entrance.EntranceView`：`main_search_container` 布局将 `id/entrance` 设为 `layout_alignParentStart`，搜索框位于其右侧；`MainSearchContainer.initView` 调用其 `bindView(Context, String)`。
- `EntranceManager.getEntranceConfig()` 提供活动图片、动画和链接配置，`EntranceView.bindView` 负责显示与点击绑定。模块单独屏蔽此 View 和绑定逻辑，不屏蔽整个搜索栏。4.126.10 上的图标屏蔽已获用户视觉确认，其他版本仍待真机验证。

## 5. 建议的模块实现结构

1. 按包名和已登记版本启用 hook；未知版本仅记录诊断，避免盲目沿用。
2. 对明确的 15 个受控偏好 key 返回目标状态，保持排除项及其他设置原行为。
3. 对存在缓存或特殊默认逻辑的 `SettingsUtils` getter 补充拦截，保证业务读取与菜单目标一致。
4. 在功能设置页创建/恢复后同步受控开关的显示状态并阻止反向切换；避免仅为了显示勾选状态而永久写入原有偏好数据。
5. 单独处理左上角活动图标的绑定/展示，并阻断关联点击与果树 SDK 启动路径；不以全局禁用 Activity 或所有 WebView 代替精确入口处理。
6. 保留原有系统能力可用性判断；“开关开启”不意味着补造设备上不存在的手机管家、权限管理或互联功能。
7. 优先采用只影响运行时的实现。预期回退方式为禁用模块并重启应用商店进程；具体回退行为须与模块一起真机验证。

## 6. 版本差异与验证记录

- s.1 与 s.2 的五个 DEX 哈希均不同，不能认定整个 APK 的代码完全相同。
- 首轮提取的 12 个目标类 smali 在 s.1 与 s.2 间逐文件一致；后续扩展到 19 个类的结果见第 8 节。4.126.10 的对应类不作相同假设。
- 三个版本的菜单 key/目标状态结构一致，15 个 getter 候选签名均存在。
- 静态检查只证明候选定位成立，不证明模块已实现或具备跨版本运行时兼容性。

可复跑验证：

```text
python -X utf8 tools/verify_analysis.py
```

首轮执行退出码为 0，输出：

```text
PASS: scripts parse; original/copy hashes match; 16 settings per version; 15 getter candidates per version; signatures valid; 12 collected classes identical between s.1 and s.2
```

逐命令参数、原始 stdout/stderr 和退出码见 `verification_commands.json`；每个版本的资源树、smali 和调用引用保存在对应 `apk_N/` 目录。

## 7. 下一步与待验证项

- 已完成静态定位、模块源码、0.1.0 单版本视觉与日志检查；1.0.0 正式版覆盖安装后需复验。
- 已连接设备型号 23117RK66C（manet），Root 日志读取成功，LSPosed 主进程注入已确认；Android/HyperOS 与框架具体版本尚未完整登记。
- 在三个应用版本分别验证冷启动、设置页重新进入、尝试反向切换、云控刷新及进程重启后状态。
- 验证目标图标消失、关联入口阻断，同时保留搜索、下载、安装、更新等核心功能。
- 单独验证“开启应用安全检测”不受规则干预，以及禁用模块后的回退行为。

## 8. StoreClean 1.0.0 发行结果

- 模块 APK：`release/storeclean-1.0.0.apk`。
- 新增源码与说明 patch：`release/storeclean-1.0.0.patch`。
- 源码归档：`release/storeclean-1.0.0-source.zip`。
- 构建验证记录：`release/storeclean-1.0.0-verification.json`。
- 回退脚本：`tools/rollback_module.py`，默认只预览，指定设备并显式传入 `--apply` 后才执行卸载模块与结束应用商店进程。
- 安装、验收与回退说明：`module/README.md`。

模块通过版本名/版本号双重匹配，仅处理登记的三个版本；共 34 个必需 hook，三个样本中的对应签名全部已通过静态检查。模块包含运行时偏好读取覆盖、受控写入拦截、缓存 getter 覆盖、菜单状态固定、左侧活动 View 屏蔽与五个果树启动重载阻断。

已完成 Java 编译、D8、APK 签名、ZIP 完整性、zipalign、模块元数据、DEX 定义类范围及源码 patch 可应用性检查。Xposed API 只用于编译，未打入 APK；APK 不包含测试类。

JVM 策略/fixture 测试验证 11 项关闭、4 项开启、安全检测及未知设置保持原值、版本门控、存储不变和恢复基线。生产回调还通过 host fake 测试，验证受控读写拦截、排除项放行、常量返回与活动 View 的隐藏及点击清除；fake 类不进入 APK。这些测试不执行真正的 Android 页面或 LSPosed 引擎；回退脚本也只验证了预览路径。真机观察独立记录于 `RUNTIME_VALIDATION.md`，设备回退仍未实测。

本轮新增证据后，s.1 与 s.2 的 19 个已提取目标类 smali 仍逐文件一致；完整记录由 `tools/verify_analysis.py` 更新。

### 8.1 发行变更

- 0.1.0 → 1.0.0，versionCode 1 → 2；显式关闭调试，包名与作用域不变。
- Hook 源码不变；构建检查旧包与新包 `classes.dex` 一致、签名证书一致，沿用现有签名以支持覆盖更新。
- 同步需求、安装/构建/回退说明及真机记录，源码归档增加项目说明和全部工具脚本。
- 0.1.0 的五个发行文件及 `module/build/0.1.0/` 已按用户要求清理；历史真机记录与 1.0.0 验证 JSON 中的基线比较结果保留。1.0.0 发行文件保持不变，其源码 ZIP/patch 是发行时快照；本次清理说明更新于工作区文档。1.0.0 尚未自动安装到设备，公开分发前仍需妥善管理现有项目签名密钥。

## 9. 1.1.0 兼容性更新（2026-10-15）

- 当前设备的 4.127.11 已完整拉取，APK SHA-256、签名、菜单结构、19 个目标类差异和调用引用均已记录，旧样本编号保持不变。
- 旧模块日志明确显示 `unsupported version: 4.127.11`。仅放开版本门控仍会被“五个重载”的旧假设阻止，且遗漏新 H5 启动路径。
- 新模块登记第四个版本，按实际启动重载解析 34 / 37 个 Hook，补齐 H5 入口；未登记 4.x 版本需完整菜单结构和全部接口匹配才尝试启用。
- 用户批准覆盖安装；1.1.0 安装成功，主进程日志确认 `hooks=37 profile=registered schema=16`。用户确认入口消失、设置开关正常；亮屏首页截图也未见左侧水果入口。
- 细节与限制见 `COMPATIBILITY_1.1.0.md`；最新发行 APK、patch、源码 ZIP 和构建验证 JSON 位于 `release/storeclean-1.1.0*`。

## 10. 1.1.1 与重复审查

当前发行产物为 `release/storeclean-1.1.1*`。新增头像图标，补强未知版本的完整果树参数、五个必需签名、返回类型、静态/实例分发以及 View/Preference 辅助接口检查；受控 key 和目标状态未改变。构建、台账与设备证据脚本的问题及回归范围见 `REVIEW_2026-10-15.md`。

目录整理后，`release/` 仅保留最新 `.apk`；对应源码 ZIP、补丁、验证 JSON 与 `.idsig` 归档到 `analysis/release_artifacts/`。新构建也采用此布局，旧章节中的发行路径属于历史记录。

成品 APK 只保留 1.1.1，历史章节中的旧 APK 路径是当时构建记录，不再表示文件仍存在；历史源码、补丁和验证 JSON 保留。最新 APK 未在设备安装，旧版的现场视觉反馈不冒充本次审查版本的实测。
