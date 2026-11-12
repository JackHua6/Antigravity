---
name: jackhua-antigravity-theme-patch
description: 华哥优化的 Antigravity 主题、字体与深度汉化增强版（v5.2.0 · 独创 Windows 客户端退出重启自动保持中文 + 白底输入框标准高对比工字型光标防隐形 + 900条深度汉化 + 昼夜双模式独立解耦）。当用户提到“重新汉化”、“汉化失效”、“升级后汉化”、“版本更新重新汉化”、“修复汉化”、“重装汉化”、“安装汉化”、“汉化”、“安装 Antigravity 主题”、“定制 Antigravity 界面样式或汉化词条”时触发。激活后直接在项目目录执行 node install.mjs install 并 verify 验收，秒级恢复全界面汉化与主题。
---

# JackHua's Antigravity 主题、字体与深度汉化增强版 (v5.2.0 · 昼夜双模式解耦 & Antigravity 2.31.0+ 全量适配)

> **前置概括（致用户与执行端 AI Agent）**：
> - **本项目基底**：基于 [Anarcadia/chuanban-antigravity-theme-patch](https://github.com/Anarcadia/chuanban-antigravity-theme-patch) 进行二次开发与深度增强，补齐了原版缺失的 **Windows 客户端退出重启自动保持中文** 与 **白底输入框鼠标工字光标 (I-beam) 标准防隐形** 两大核心体验能力。
> - **设计目的**：以纯运行时 CDP 非侵入式注入，为 Google Antigravity 提供昼夜双模式物理隔离、900条深度汉化与实时模型指标，并实现 Windows 平台日常无感常驻：
>   - **白天模式（`body:not(.dark)`）**：提供三套 Anthropic 暖纸护眼配色预设（默认高对比暖白）与输入框「古朴暗红蜡封」三态交互；
>   - **黑夜模式（`body.dark`）**：当点击客户端「深色 / Dark」按钮切换时，**100% 保持四层字体排版与 UI 几何形状不变**，同时 `0ms` 还原 Antigravity `2.31.0` 官方 `onyx` Default Dark 碳黑配色方案；
>   - **光标防隐形与色彩校正（v5.2.0 优化特性）**：恢复系统标准默认粗细与大小的工字指针（1px 纤细主干），通过上下文色彩方案强制声明，白天锁定纯黑、黑夜自动切换纯白，点选字与字之间精准绝不遮挡；
>   - **双启动联合守护（v5.2.0 独创新特性）**：安装时自动感知并绑定桌面与开始菜单快捷方式（`LaunchAntigravity.vbs`），客户端退出重启、电脑关机开机 **100% 自动保持中文**，告别单次生效！
>   - **全局共享能力**：四层中西文精密排版、900 条全界面无死角汉化及基于 SQLite `O(1)` 增量游标的同行实时会话指标胶囊（`tok/s · TTFT · Ctx 256k 水位 · Out`）。

---

## 一、核心资源链接

1. **GitHub 权威代码库（本增强版仓库）**
   - 仓库：<https://github.com/JackHua6/Antigravity>
2. **Google Drive 完全资源包（全套商业/开源字体库）**
   - 链接：<https://drive.google.com/drive/folders/1NX92SgVUqtSjWg6bt6sIJXy-cn7J_boC>
   - 包含：全套必备字体包（Anthropic 官方字体族 `Anthropic Sans` / `Anthropic Serif` / `Anthropic Mono` + 更纱黑体 `Sarasa-SuperTTC.ttc` 超集）。
3. **上游原作者仓库（致敬与鸣谢）**
   - 仓库：<https://github.com/Anarcadia/chuanban-antigravity-theme-patch>

---

## 二、AI Agent 标准部署流程（3 步极简闭环）

当用户要求安装或更新本补丁时，请按顺序执行以下 3 步：

### Step 1：环境与字体前置检查
```bash
node install.mjs doctor
```

### Step 2：一键安装并自动注册守卫
```bash
node install.mjs install
```
`install.mjs install` 在 Windows 端会自动完成：
1. 校验 `core/manifest.json` SHA-256 完整性并原子安装内核；
2. 注入双层矢量高对比工字型光标与高对比暖白主题；
3. **自动生成 `LaunchAntigravity.vbs` 并绑定桌面与开始菜单快捷方式**，实现退出重启自动保持中文；
4. 生成离线一键修复脚本 `重新汉化.bat`，并注册 Windows 自启服务。

### Step 3：CDP 实机注入验收
```bash
node install.mjs verify
```
当终端输出 `"ok": true` 时即代表注入成功。

---

## 三、Windows (`win32`) 增强特性深度说明

1. **Windows 快捷方式双启动联合守护机制**：
   - 原版通过纯子进程拉起，在 Antigravity 退出时会被 Windows 作业对象连带销毁，导致下次由桌面图标启动时丢失汉化；
   - 本版通过 `LaunchAntigravity.vbs` 与快捷方式无缝绑定，每次用户双击桌面图标启动 Antigravity，脚本会在 0 秒内检测守护状态并在后台静默拉起，客户端主窗口就绪后 1~2 秒内自动注入汉化，彻底解决重启变英文的困扰。
2. **Chromium DWM 白底输入框工字光标防隐形**：
   - 针对 Windows DWM 硬件加速反色错误的问题，本版直接在 `core/theme.css` 中注入了 SVG 矢量物理光标规则，强制锁定 `caret-color: #000000` 与纯黑带防反光微轮廓光标，黑夜模式下则自适应纯白高光，全天候清晰可见。
3. **智能指令自愈体系**：
   - 面对未来 Antigravity 大版本覆盖更新，用户只需直接发一句话：`重新汉化`、`修复汉化` 或 `汉化失效了`，Agent 即可依据本 `SKILL.md` 触发词自动秒级恢复。
