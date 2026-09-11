# Voice Vibe 语音输入

按住热键说话 → 松开后自动润色 → 文字粘贴到当前光标处。参考 [OpenLess](https://github.com/Open-Less/openless)（Wispr Flow 开源替代）与 [蛐蛐 QuQu](https://github.com/yan5xu/ququ) 的产品思路，用 Python 实现的 Windows 桌面语音输入工具。

## 功能

| 热键（默认） | 模式 | 说明 |
|---|---|---|
| 按住 **F2** | 简单润色 | 规则引擎本地瞬时处理：删除语气词（嗯/呃/啊…）、折叠口吃重复、整理标点、中英文间补空格 |
| 按住 **F3** | 深度润色 | LLM 提示词工程：把口语内容重写为结构化 AI 提示词（角色/任务/约束/输出格式） |
| 按住 **F4** | 原始转写 | 不做任何处理直接上屏 |
| **Esc** | 取消 | 录音过程中取消本次输入 |

- 流式识别：边说边出字（阿里云 Paraformer 实时语音识别，服务端同时过滤语气词）
- 悬浮条：显示状态、流式文字、音量波形，可拖动，不抢焦点
- 历史记录：每次输入落盘 `history.jsonl`，托盘可查看
- 深度润色失败自动降级为简单润色

## 快速开始

**方式一（推荐）：一键启动**

双击 `start_voice_vibe.bat` 即可。脚本会自动完成：依赖检查与安装（首次）→ 首次运行生成 `config.toml` 并打开记事本引导你填 API Key → 以无黑窗口的后台方式启动应用（已在运行则不重复启动）。

> 若 Python 不在 `D:\Python3.13`，右键编辑 bat 修改开头的 `PY` / `PYW` 两行。

**方式二：手动命令行**

```bash
# 1. 安装依赖（Python 3.12+；本项目在 D:\Python3.13 验证通过）
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 2. 配置
copy config.example.toml config.toml
# 编辑 config.toml：
#   [asr]  api_key = "sk-…"        ← 阿里云百炼 DashScope Key（实时识别，有免费额度）
#   [llm]  api_key = "…"           ← 任意 OpenAI 兼容 Key（深度润色用，可选）
#   开通 DashScope：https://bailian.console.aliyun.com/ → API-KEY 管理

# 3. 运行
python main.py
```

启动后最小化到托盘（麦克风图标），屏幕底部出现悬浮条。在任意输入框中：按住 F2 说话 → 松开 → 文字自动粘贴到光标处。

### 获取 API Key

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
| `[hotkey]` | `simple` / `deep` / `raw` / `cancel` | 热键绑定（keyboard 库键名，如 `f2`、`ctrl+space`） |
| `[audio]` | `device` | 麦克风序号，`-1` 为系统默认；用 `python -m sounddevice` 查看设备列表 |
| `[polish]` | `simple_llm_coherence` | 简单润色后追加 LLM 连贯性处理（默认关，保持瞬时） |
| `[ui]` | `x` / `y` | 悬浮条位置（拖动后自动保存） |

也可直接在托盘菜单 →「设置」里修改。

## 项目结构

```
main.py                  入口 + 总控（状态机：idle→starting→recording→finalizing）
app/
  config.py              TOML 配置读写
  recorder.py            sounddevice 16k PCM 采集
  hotkey.py              全局热键（按住/松开，忽略按键重复）
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
tests/test_simple_polish.py   润色规则单元测试
```

## 测试

```bash
python -m pytest tests/ -v
```

## 已知取舍

- 文字注入用「剪贴板 + Ctrl+V」实现，粘贴后 1.2 秒恢复原剪贴板内容；这 1 秒多内复制的内容会被短暂覆盖。
- LLM 键位若配了 F 键，笔记本可能需要 Fn 组合；可在设置中改为其他键。
- 若 PyPI 安装超时，使用国内镜像（见快速开始命令）。
