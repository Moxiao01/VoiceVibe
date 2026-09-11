"""简单润色：纯规则、离线、毫秒级。

处理内容：
- 删除语气词（嗯/呃/啊/哦…），整句、句首、独立成段都能处理
- 删除分句开头的口头语（然后/就是/其实/就是说/反正/而且/怎么说呢…）
- 折叠口吃重复（"那个那个那个" → "那个"），删除独占分句的犹豫语"那个/这个"
- 英文填充词（um/uh/erm）
- 清理冗余标点与空白，中文与英文/数字之间补空格
策略取舍：句首口头语一律删，极少数列举语义的"然后"会被误删；
"这个/那个"是常用指示词，只在独占分句时删，"那个方案"这类用法保留。
"""
from __future__ import annotations

import re

# 无歧义语气词（出现在词首也不会是正常词的开头）
_FILLER_CHARS = "嗯呃啊哦噢喔唔诶哎唉"
# 语气词连用，如 "嗯嗯"、"呃啊"
_FILLER_RUN = re.compile(rf"^(?:[{_FILLER_CHARS}]{{1,3}})+")
# 语气词独占一个分句，如 "今天天气不错，呃，我们去爬山" 中间的 "呃"
_FILLER_SEGMENT = re.compile(rf"^(?:[{_FILLER_CHARS}]{{1,3}})+$")
# 口吃重复的指示/连接词：出现 2 次以上视为口吃，折叠为 1 次
_STUTTER_WORDS = ("那个", "这个", "就是说", "然后", "就是", "所以", "但是", "其实", "反正")
_STUTTER_REPEAT = re.compile(
    "^(" + "|".join(_STUTTER_WORDS) + r")(?:\1)+"
)
# 分句开头的口头语：独立出现也删（按长短排序，避免"就是"截胡"就是说"）。
# "那么"后跟程度词时是"那么多/那么大"，要保留
_DEGREE_AFTER_SO = "多大小高低好坏快慢久远近少长短深浅厚薄重轻"
_OPEN_FILLER_RE = re.compile(
    "^(?:怎么说呢|就是说呢|就是说|然后呢|然后吧|然后|其实呢|其实吧|其实|反正呢|反正"
    rf"|而且|那么(?![{_DEGREE_AFTER_SO}])|就是)"
)
# 独占一个分句的口头语（"帮我写个，那个，脚本"），连同标点一起丢弃
_STANDALONE_FILLERS = {
    "那个", "这个", "就是", "就是呢", "就是说", "然后", "然后呢",
    "其实", "其实呢", "反正", "那么", "而且", "对吧", "是吧",
}
# 英文填充词
_EN_FILLER = re.compile(r"\b(?:um+|uh+|erm)\b[ \t]*", re.IGNORECASE)
# 冗余标点
_REPEATED_PUNCT = re.compile(r"([，。！？；、,.!?;：:])\1+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([，。！？；、,.!?;：:])")
_LEADING_PUNCT = re.compile(r"^([，。！？；、,\.!?;：:])+")
_CJK = r"\u4e00-\u9fff"
_CJK_LATIN_GAP = re.compile(rf"([{_CJK}])([A-Za-z0-9])|([A-Za-z0-9])([{_CJK}])")

# 分句切分（保留分隔符）
_SEGMENT_SPLIT = re.compile(r"([，。！？；、,.!?;：:\n])")


def _clean_segment(segment: str) -> str:
    s = segment.strip()
    # 反复剥离句首废话，覆盖"然后就是其实…"这类连用
    for _ in range(6):
        before = s
        s = _FILLER_RUN.sub("", s)
        s = _STUTTER_REPEAT.sub(r"\1", s)
        s = _OPEN_FILLER_RE.sub("", s, count=1)
        if s == before:
            break
        s = s.lstrip()
    return s.strip()


def simple_polish(text: str) -> str:
    if not text or not text.strip():
        return ""
    text = _EN_FILLER.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)

    parts = _SEGMENT_SPLIT.split(text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # 分隔符：仅当前面保留下来的分句非空时才保留
            if out and out[-1].strip():
                out.append(part)
            continue
        seg = _clean_segment(part)
        if not seg:
            continue  # 语气词/口头语独占分句 → 连同它的标点一起丢弃
        if seg in _STANDALONE_FILLERS:
            continue
        out.append(seg)
    text = "".join(out)

    text = _REPEATED_PUNCT.sub(r"\1", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _LEADING_PUNCT.sub("", text)
    # 中英文/数字之间补空格（盘古之白），如 "用python写" → "用 python 写"
    prev = None
    while prev != text:
        prev = text
        text = _CJK_LATIN_GAP.sub(
            lambda m: (m.group(1) + " " + m.group(2)) if m.group(1) else (m.group(3) + " " + m.group(4)),
            text,
        )
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
