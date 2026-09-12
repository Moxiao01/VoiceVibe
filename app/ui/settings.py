"""设置对话框与历史记录窗口。"""
from __future__ import annotations

from copy import deepcopy

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..config import Config, save_config
from ..history import load_records

_MODE_NAMES = {"simple": "简单润色", "deep": "深度润色", "raw": "原始转写"}


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, on_saved, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Voice Vibe 设置")
        self.setMinimumWidth(520)
        self._cfg = cfg
        self._on_saved = on_saved

        form = QFormLayout()

        self.asr_key = QLineEdit(cfg.asr.api_key)
        self.asr_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.asr_key.setPlaceholderText("阿里云百炼 DashScope API Key（sk-…）")
        form.addRow("识别 API Key", self.asr_key)

        self.asr_model = QLineEdit(cfg.asr.model)
        form.addRow("识别模型", self.asr_model)

        self.asr_base = QLineEdit(cfg.asr.base_url)
        self.asr_base.setPlaceholderText("留空 = 官方国内站；国际站填 dashscope-intl.aliyuncs.com")
        form.addRow("识别服务地址", self.asr_base)

        self.llm_base = QLineEdit(cfg.llm.base_url)
        form.addRow("LLM Base URL", self.llm_base)

        self.llm_key = QLineEdit(cfg.llm.api_key)
        self.llm_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_key.setPlaceholderText("OpenAI 兼容接口的 API Key")
        form.addRow("LLM API Key", self.llm_key)

        self.llm_model = QLineEdit(cfg.llm.model)
        form.addRow("LLM 模型", self.llm_model)

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 1.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(cfg.llm.temperature)
        form.addRow("LLM temperature", self.temperature)

        self.coherence = QCheckBox("简单润色后追加 LLM 连贯性处理（需配置 LLM，失败自动回退）")
        self.coherence.setChecked(cfg.polish.simple_llm_coherence)
        form.addRow("", self.coherence)

        self.hotkey_mode = QComboBox()
        self.hotkey_mode.addItem("按住说话（按住开始，松开结束）", "hold")
        self.hotkey_mode.addItem("切换模式（按一下开始，再按一下结束）", "toggle")
        current = (cfg.hotkey.mode or "hold").strip().lower()
        idx = self.hotkey_mode.findData(current)
        self.hotkey_mode.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("热键触发方式", self.hotkey_mode)

        hotkey_row = QHBoxLayout()
        self.hk = {}
        for mode in ("simple", "deep", "raw", "cancel"):
            edit = QLineEdit(getattr(cfg.hotkey, mode))
            edit.setMaximumWidth(90)
            self.hk[mode] = edit
            hotkey_row.addWidget(QPushButton(_MODE_NAMES.get(mode, mode) + "："), 0)
            hotkey_row.addWidget(edit)
        hotkey_row.addStretch(1)
        form.addRow("热键", hotkey_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        # 从当前配置拷贝再覆盖表单字段；新建默认 Config 会把麦克风、悬浮条位置等
        # 对话框未覆盖的字段冲回默认值
        cfg = deepcopy(self._cfg)
        cfg.asr.api_key = self.asr_key.text().strip()
        cfg.asr.model = self.asr_model.text().strip() or cfg.asr.model
        cfg.asr.base_url = self.asr_base.text().strip()
        cfg.llm.base_url = self.llm_base.text().strip()
        cfg.llm.api_key = self.llm_key.text().strip()
        cfg.llm.model = self.llm_model.text().strip() or cfg.llm.model
        cfg.llm.temperature = self.temperature.value()
        cfg.polish.simple_llm_coherence = self.coherence.isChecked()
        for mode, edit in self.hk.items():
            setattr(cfg.hotkey, mode, edit.text().strip().lower() or mode)
        cfg.hotkey.mode = self.hotkey_mode.currentData() or "hold"
        save_config(cfg)
        self._on_saved(cfg)
        self.accept()


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Voice Vibe 历史记录")
        self.resize(720, 480)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlaceholderText("暂无历史记录")

        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.reload)
        clear = QPushButton("打开记录文件")
        clear.clicked.connect(self._open_file)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh)
        buttons.addWidget(clear)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)
        layout.addLayout(buttons)
        self.reload()

    def reload(self) -> None:
        records = load_records(300)
        if not records:
            self.view.setPlainText("")
            return
        lines = []
        for r in records:
            mode = _MODE_NAMES.get(r.get("mode"), r.get("mode", "?"))
            lines.append(f"[{r.get('time', '')}] {mode}（{(r.get('duration_ms', 0) / 1000):.1f}s）")
            lines.append(f"  原文：{r.get('raw', '')}")
            lines.append(f"  上屏：{r.get('final', '')}")
            lines.append("")
        self.view.setPlainText("\n".join(lines))

    def _open_file(self) -> None:
        import subprocess
        from pathlib import Path

        from ..history import HISTORY_PATH

        if not HISTORY_PATH.exists():
            Path(HISTORY_PATH).touch()
        subprocess.Popen(["notepad.exe", str(HISTORY_PATH)])
