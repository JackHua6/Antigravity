# 📊 AI Token 工作台看板（本地离线单文件版）

> 一键扫描你本机所有 AI 编程/办公软件的本地会话日志，生成零依赖、深色现代风格的 **单文件交互式 HTML 数据看板**。  
> 所有统计与解析均**100% 在本机完成**，不联网上传任何代码目录或聊天日志。

---

## ✨ 核心功能

- **多客户端统一聚合**：基于 `tokscale` 本地引擎，支持 **Antigravity、Claude Code、Codex、Cursor、Windsurf、WorkBuddy、Trae、ZCode、Qoder、Cline、Roo Code、Gemini CLI、OpenCode、Kimi、Qwen** 等 60+ 客户端；并在 Windows 端原生内置 **豆包工作 (DouBao Work)** 本地轨迹解析。
- **6 级 GitHub 风格消费热力图**：支持按 `Token / 费用 ($) / 活跃时长` 与 4 套配色（翡翠绿 / 科技青 / 烈焰橙 / 雅紫罗兰）切换，点击任意日期可下钻查看当天分软件/分模型流水。
- **精准会话时长 & 并发统计**：覆盖 `全部历史 / 近 30 天 / 本月 / 近 7 天` 及**任意自定义日期区间**的活跃时长、会话数、最长连续工作时长与速率。
- **全量 vs 净新增口径切换**：支持一键剔除 `Cache Read`，横向公平对比 `Anthropic`（显式 Cache Write）与 `OpenAI / Google / 国产模型` 的真实新增上下文消耗。
- **独立 24 小时工作节律**：分客户端精确采集，筛选单一软件时也能准确反映该工具的小时级使用习惯。
- **一键隐私脱敏 & 明细导出**：内置「🙈 隐私脱敏」按钮，可一键隐藏所有真实本地目录名方便截图分享；支持导出 UTF-8-SIG 格式 CSV（Excel 打开无乱码）。

---

## 🚀 快速开始

### 前置环境（仅需这两项）
1. **Python 3.9+**（Windows 安装时请勾选 *Add Python to PATH*）
2. **Node.js 18+**（建议先执行一次全局安装以加速扫描：`npm install -g tokscale`；若不全局安装，首次运行时脚本也会自动尝试通过 `npx` 拉取）

### 启动方式
- **Windows**：直接双击目录中的 **`刷新并打开看板.bat`**，等待数秒自动扫描并打开浏览器。
- **macOS / Linux**：在终端运行：
  ```bash
  chmod +x refresh.sh
  ./refresh.sh
  ```
- **仅更新数据不弹窗（适用于定时任务 / CI / 命令行）**：
  ```bash
  python3 refresh_dashboard.py --no-open
  ```

---

## 🤖 发给 AI Agent 一键配置（推荐）

如果你的某些 AI 客户端日志装在自定义目录，或者本机缺少依赖，可直接把本文件夹路径发给你的 AI 助手（Antigravity / Claude Code / Codex / Cursor）：

> 请帮我运行 `token-dashboard/` 下的 `refresh_dashboard.py` 刷新本机 AI Token 看板；如果报错缺依赖或未扫描到我常用软件的自定义目录，请帮我检查环境并适配路径后重新运行。

---

## ❓ 常见问题排查

| 现象 | 原因与解决方法 |
| :--- | :--- |
| 打开 `token_dashboard.html` 显示“尚未扫描本机日志” | 模板默认不含任何个人隐私数据，请先双击运行一次 `刷新并打开看板.bat`（或 `refresh.sh`）生成本地快照。 |
| 报错 `未检测到 tokscale 或 Node.js` | 请确认系统已安装 Node.js 且 `npm install -g tokscale` 可正常执行；如安装在自定义路径，可设置环境变量 `TOKSCALE_BIN=/你的路径/tokscale`。 |
| 某个新装或冷门工具没被统计到 | 请先在命令行运行 `tokscale clients` 查看该工具是否已被 `tokscale` 扫描识别，确认后重新刷新看板即可。 |
| 截图分享不想暴露本地项目文件夹路径 | 点击看板右上角的 **「🙈 隐私脱敏」** 按钮，即刻匿名化显示所有工作区路径（刷新页面或再次点击即可恢复）。 |
