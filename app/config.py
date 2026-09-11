"""配置读写：config.toml（项目根目录），缺失字段回退默认值。"""
from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.toml"


@dataclass
class AsrConfig:
    api_key: str = ""
    model: str = "paraformer-realtime-v2"
    base_url: str = ""  # 留空 = 官方国内站；可填域名或完整 WebSocket 地址
    disfluency_removal: bool = True  # 服务端过滤语气词（嗯/啊等）


@dataclass
class LlmConfig:
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    api_key: str = ""
    model: str = "glm-4-flash"
    temperature: float = 0.3
    timeout: int = 20


@dataclass
class HotkeyConfig:
    simple: str = "f2"
    deep: str = "f3"
    raw: str = "f4"
    cancel: str = "esc"


@dataclass
class AudioConfig:
    device: int = -1  # -1 = 系统默认麦克风
    sample_rate: int = 16000


@dataclass
class PolishConfig:
    simple_llm_coherence: bool = False


@dataclass
class InputConfig:
    streaming: bool = True  # 说话时把文字实时打进光标处并同步修正（深度润色不适用）


@dataclass
class UiConfig:
    x: int = -1  # -1 = 底部居中
    y: int = -1


@dataclass
class Config:
    asr: AsrConfig = field(default_factory=AsrConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    polish: PolishConfig = field(default_factory=PolishConfig)
    input: InputConfig = field(default_factory=InputConfig)
    ui: UiConfig = field(default_factory=UiConfig)

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm.api_key and self.llm.model)

    @property
    def asr_ready(self) -> bool:
        return bool(self.asr.api_key)


def _merge(cls, data: dict):
    """用 dict（部分字段）构造 dataclass，忽略未知字段，类型尽量校正。"""
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        ftype = f.type if isinstance(f.type, str) else getattr(f.type, "__name__", str(f.type))
        if ftype == "bool" and isinstance(value, str):
            value = value.lower() in ("true", "1", "yes")
        elif ftype == "int" and not isinstance(value, bool):
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        kwargs[f.name] = value
    return cls(**kwargs)


def load_config() -> Config:
    cfg = Config()
    if not CONFIG_PATH.exists():
        return cfg
    try:
        with open(CONFIG_PATH, "rb") as fp:
            data = tomllib.load(fp)
    except tomllib.TOMLDecodeError as exc:
        print(f"[config] config.toml 解析失败，使用默认配置：{exc}")
        return cfg
    for section, cls in (
        ("asr", AsrConfig),
        ("llm", LlmConfig),
        ("hotkey", HotkeyConfig),
        ("audio", AudioConfig),
        ("polish", PolishConfig),
        ("input", InputConfig),
        ("ui", UiConfig),
    ):
        if isinstance(data.get(section), dict):
            setattr(cfg, section, _merge(cls, data[section]))
    return cfg


def save_config(cfg: Config) -> None:
    """把配置写回 config.toml（设置对话框用）。"""
    lines = []
    for section in ("asr", "llm", "hotkey", "audio", "polish", "input", "ui"):
        lines.append(f"[{section}]")
        for key, value in asdict(getattr(cfg, section)).items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, str):
                rendered = json.dumps(value, ensure_ascii=False)
            else:
                rendered = str(value)
            lines.append(f"{key} = {rendered}")
        lines.append("")
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")
