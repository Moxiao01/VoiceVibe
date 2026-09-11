"""简单润色规则引擎的单元测试。运行：python -m pytest tests/ -v 或 python -m unittest discover tests"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.polish.simple import simple_polish


def test_remove_leading_fillers():
    assert simple_polish("嗯，帮我写一个Python脚本") == "帮我写一个 Python 脚本"
    assert simple_polish("呃啊，今天天气不错") == "今天天气不错"
    assert simple_polish("嗯嗯嗯我想想") == "我想想"


def test_remove_filler_segment():
    assert simple_polish("今天天气不错，呃，我们去爬山") == "今天天气不错，我们去爬山"
    assert simple_polish("帮我写个，那个，脚本") == "帮我写个，脚本"


def test_collapse_stutter():
    assert simple_polish("那个那个那个帮我打开文件") == "那个帮我打开文件"
    assert simple_polish("然后然后我们就走了") == "然后我们就走了"


def test_english_fillers():
    assert simple_polish("um let me think about it") == "let me think about it"


def test_punctuation_cleanup():
    assert simple_polish("好的！！！") == "好的！"
    assert simple_polish("，，测试一下") == "测试一下"
    assert simple_polish("测试 ， 一下") == "测试，一下"


def test_cjk_latin_spacing():
    assert simple_polish("用python写代码，部署到docker") == "用 python 写代码，部署到 docker"


def test_preserves_meaning():
    # 非语气词开头的正常内容不能被误删
    assert simple_polish("额外帮我加个功能") == "额外帮我加个功能"
    assert simple_polish("这个方案不错") == "这个方案不错"
    assert simple_polish("然后我们再讨论细节") == "然后我们再讨论细节"


def test_empty_and_pure_filler():
    assert simple_polish("") == ""
    assert simple_polish("   ") == ""
    assert simple_polish("嗯啊呃") == ""


def test_mixed_full_sentence():
    text = "嗯，就是那个那个帮我把，呃，main.py里的bug修一下，然后重新跑一遍测试"
    result = simple_polish(text)
    assert "嗯" not in result.replace("然后", "")
    assert "呃" not in result
    assert "main.py" in result
