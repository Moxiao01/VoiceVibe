# Voice Vibe 语音输入

**按住热键说话 → 松开后自动润色 → 文字粘贴到当前光标处。**（触发方式可改为切换模式：按一下开始，再按一下结束，托盘「设置」里配置）

Windows 桌面语音输入工具，参考 [OpenLess](https://github.com/Open-Less/openless)（Wispr Flow 开源替代）与 [蛐蛐 QuQu](https://github.com/yan5xu/ququ) 的产品思路，用 Python 实现。目标是在任何输入框里，让"说话"像打字一样可用——但快得多。

## 功能特性

| 热键（默认） | 模式 | 说明 |
|---|---|---|
| 按住 **F2** | 简单润色 | 规则引擎本地瞬时处理：删除语气词（嗯/呃/啊…）、删除句首口头语（然后/就是/其实…）、折叠口吃重复、整理标点、中英文间补空格 |
| 按住 **F3** | 深度润色 | LLM 提示词工程：把口语内容重写为结构化 AI 提示词（角色/任务/约束/输出格式） |
| 按住 **F4** | 原始转写 | 不做任何处理直接上屏 |
| **Esc** | 取消 | 录音过程中取消本次输入 |

- **流式实时上屏**：边说边出字并实时打进当前光标处（阿里云 DashScope 实时语音识别）；简单润色/原文模式下，语气词删除会同步修正到输入框，深度润色除外
- **悬浮条**：显示状态、流式文字、音量波形，可拖动、不抢焦点；录音时右侧有 ⏸ 停止按钮，点击等同松开热键——正常结束并保留本次文字（Esc 才是取消，会撤销已打入的文字）
- **历史记录**：每次输入落盘 `history.jsonl`，托盘菜单可查看
- **降级容错**：深度润色失败自动降级为简单润色，流式中断自动回退为"松开后整段粘贴"；识别服务中断时等同松手——立即停麦、收尾并上屏中断前已识别的部分，不会出现"界面复位但录音仍在后台跑"的失同步
- **托盘常驻 + 单实例**：Windows 命名互斥体防重复启动，配置可视化修改

## 安装使用

### 方式一：安装包（推荐普通用户）

从 [Releases](https://github.com/Moxiao01/VoiceVibe/releases) 下载 `VoiceVibe-Setup-x.y.z.exe` 双击安装。

- 首次运行会在 `%APPDATA%\VoiceVibe` 生成 `config.toml`，通过托盘「设置」或直接编辑该文件填入 API Key（见下文[获取 API Key](#获取-api-key)）
- 开机自启可将 `VoiceVibe.exe` 的快捷方式放入 `shell:startup`

### 方式二：源码运行（Python 3.12+）

**一键启动**：双击 `start_voice_vibe.bat`。脚本会自动完成：依赖检查与安装（首次）→ 首次运行生成 `config.toml` 并打开记事本引导你填 API Key → 以无黑窗口的后台方式启动应用（已在运行则不重复启动）。

> 若 Python 不在 `D:\Python3.13`，右键编辑 bat 修改开头的 `PY` / `PYW` 两行。

**手动命令行**：

```bash
# 1. 安装依赖
python -m pip install -r requirements.txt

# 2. 配置
copy config.example.toml config.toml
# 编辑 config.toml 填入 API Key（见下文）

# 3. 运行
python main.py
```

启动后最小化到托盘（麦克风图标），屏幕底部出现悬浮条。在任意输入框中：按住 F2 说话 → 松开 → 文字自动粘贴到光标处（可在设置里改为切换模式：按一下开始、再按一下结束）。

## 获取 API Key

- **语音识别（必填）**：[阿里云百炼](https://bailian.console.aliyun.com/) 开通后创建 API-KEY。默认模型 `paraformer-realtime-v2`，按秒计费、新用户有免费额度。
- **深度润色 LLM（F3 用，可选）**：`config.toml` 的 `[llm]` 段填任意 OpenAI 兼容服务，例如：
  - 智谱：`base_url = "https://open.bigmodel.cn/api/paas/v4"`，`model = "glm-4-flash"`
  - 通义：`base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"`，`model = "qwen-plus"`
  - Kimi：`base_url = "https://api.moonshot.cn/v1"`
  - 本地 Ollama：`base_url = "http://localhost:11434/v1"`

## 配置项（config.toml）

| 段 | 键 | 说明 |
|---|---|---|
| `[asr]` | `api_key` / `model` / `base_url` / `disfluency_removal` | 识别 Key、模型名、服务地址（留空=官方国内站，国际站填 `dashscope-intl.aliyuncs.com`）、服务端语气词过滤开关 |
| `[llm]` | `base_url` / `api_key` / `model` / `temperature` / `timeout` | 深度润色的大模型 |
| `[hotkey]` | `simple` / `deep` / `raw` / `cancel` / `mode` | 热键绑定（keyboard 库键名，如 `f2`、`ctrl+space`）；`mode` 为触发方式：`hold` 按住说话 / `toggle` 按一下开始再按一下结束 |
| `[audio]` | `device` | 麦克风序号，`-1` 为系统默认；用 `python -m sounddevice` 查看设备列表 |
| `[polish]` | `simple_llm_coherence` | 简单润色后追加 LLM 连贯性处理（默认关，保持瞬时） |
| `[input]` | `streaming` | 实时上屏开关（关闭后恢复为松开热键后整段粘贴） |
| `[ui]` | `x` / `y` | 悬浮条位置（拖动后自动保存） |

也可直接在托盘菜单 →「设置」里修改。

## 打包发布

从源码构建 Windows 安装包（onedir 模式，启动快、杀软误报少）：

```bash
# 1. 生成 dist\VoiceVibe\（需已安装 pyinstaller）
packaging\build_exe.bat

# 2. 封装安装包 dist\VoiceVibe-Setup-<版本>.exe（需 Inno Setup 6）
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\voice_vibe.iss
```

## 项目结构

```
main.py                  入口 + 总控（状态机：idle→starting→recording→finalizing）
app/
  config.py              TOML 配置读写（打包版数据目录迁移 %APPDATA%\VoiceVibe）
  recorder.py            sounddevice 16k PCM 采集
  hotkey.py              全局热键（按住/松开或单键切换，忽略按键重复）
  inject.py              剪贴板 + Ctrl+V 注入，延迟恢复原剪贴板
  history.py             JSONL 历史记录
  asr/
    base.py              流式引擎抽象（可扩展本地/其他云端引擎）
    dashscope_rt.py      DashScope Paraformer 实时识别
  polish/
    simple.py            规则润色（语气词/口吃/标点/盘古之白）
    prompts.py           润色提示词模板
    llm.py               OpenAI 兼容客户端
    deep.py              连贯润色 + 提示词化
  ui/
    overlay.py           置顶悬浮条（状态点/流式文字/波形）
    tray.py              托盘
    settings.py          设置对话框 + 历史窗口
packaging/               PyInstaller spec、Inno Setup 脚本、图标
tests/                   润色规则/配置/引擎/上屏/发布流程等单元测试
```

## 测试

```bash
python -m pytest tests/ -v
```

## 已知取舍

- 文字注入用「剪贴板 + Ctrl+V」实现，粘贴后 1.2 秒恢复原剪贴板内容；这 1 秒多内复制的内容会被短暂覆盖。
- 实时上屏按"字符退格 + 增量粘贴"修正：说话过程中若移动了光标或切换了窗口，文字可能打进错误位置；不支持 Ctrl+V 的程序（部分终端）不适用。流式中断时自动回退为"松开后整段粘贴"，可用 `config.toml` 的 `[input] streaming` 关闭实时上屏。
- 简单润色的句首口头语一律删除，极少数列举语义的"然后"会被误删。
- LLM 键位若配了 F 键，笔记本可能需要 Fn 组合；可在设置中改为其他键。
- 若 PyPI 安装超时，使用国内镜像（如 `https://pypi.tuna.tsinghua.edu.cn/simple`）。

## 许可证

[MIT](LICENSE)
