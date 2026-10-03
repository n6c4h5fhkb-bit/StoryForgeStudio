"""Catch things in a compiled prompt that the video model should never see."""
from __future__ import annotations

import re

from .model import Issue

META_PHRASES = ('剪辑余量', '参考计划', '尚未物化', '上传参考图', '切镜依据', '随后切镜', '不提前表演', '伤未宣称',
                '本镜约第', '起始组合', '结束组合', '补充状态', '__母图__', '__子图__', '镜头阶段', '持有关系', '状态为',
                '待生成', '占位', '观众先知道', '禁止将')
ASCII = re.compile(r'[A-Za-z][A-Za-z0-9_]+')


def author_words(*texts: str) -> set[str]:
    """ASCII words the author wrote on purpose (KTV, ICU...) are allowed through."""
    words = set()
    for text in texts:
        words |= set(ASCII.findall(text or ''))
    return words


def lint_prompt(text: str, where: str, cap: dict, allowed: set[str]) -> list[Issue]:
    issues = []
    stray = sorted(set(ASCII.findall(text)) - allowed)
    if stray:
        issues.append(Issue('warning', 'PROMPT_ASCII', where, f'提示词里有英文或代码：{"、".join(stray)}'))
    meta = [phrase for phrase in META_PHRASES if phrase in text]
    if meta:
        issues.append(Issue('warning', 'PROMPT_META', where, f'提示词里有写给作者或工具的话：{"、".join(meta)}'))
    low, high = cap.get('prompt_chars', [0, 10 ** 9])
    if len(text) > high:
        issues.append(Issue('warning', 'PROMPT_LONG', where, f'提示词 {len(text)} 字，超过建议上限 {high} 字；拆分请求或精简画面描述'))
    if re.search(r'\d+\.\d+\s*秒', text):
        issues.append(Issue('warning', 'PROMPT_DECIMAL', where, '时间码带小数；模型按整秒理解'))
    if '。。' in text or '，，' in text:
        issues.append(Issue('info', 'PROMPT_PUNCT', where, '重复标点'))
    return issues
