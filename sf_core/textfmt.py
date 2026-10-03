"""Small text helpers shared by the parsers and the renderer."""
from __future__ import annotations

import re

COLON = re.compile(r'[：:]')
LIST_SEP = re.compile(r'\s*[,，、;；/]\s*')
EMPTY_MARKS = {'', '-', '—', '——', '无', '空', 'none'}
PUNCT = set('，。！？、；：“”‘’…—,.!?;:"\'()（）《》【】[]·-~～ \t')
ASCII_WORD = re.compile(r'[A-Za-z]+')


def split_kv(text: str):
    """Split 'key：value' at the first full-width or ASCII colon."""
    match = COLON.search(text)
    if not match:
        return None
    return text[:match.start()].strip(), text[match.end():].strip()


def split_list(text: str) -> list[str]:
    text = (text or '').strip()
    if text in EMPTY_MARKS:
        return []
    return [item for item in (part.strip() for part in LIST_SEP.split(text)) if item and item not in EMPTY_MARKS]


def spoken_chars(text: str) -> float:
    """Approximate syllables: CJK characters and digits count 1, ASCII letters 0.5."""
    total = 0.0
    for char in text or '':
        if char in PUNCT or char.isspace():
            continue
        total += 0.5 if char.isascii() and char.isalpha() else 1.0
    return total


def strip_paren(text: str):
    """Split a leading parenthetical: '（低声）你来了' -> ('低声', '你来了')."""
    text = text.strip()
    match = re.match(r'^[（(]([^）)]{0,20})[）)]\s*', text)
    if not match:
        return '', text
    return match.group(1).strip(), text[match.end():].strip()


def tidy(text: str) -> str:
    """Normalize generated Chinese prose: no doubled punctuation, no stray spaces."""
    text = re.sub(r'[ \t]+', ' ', text.strip())
    text = re.sub(r'([。！？])[。]+', r'\1', text)
    text = re.sub(r'[，、]+([。！？])', r'\1', text)
    text = re.sub(r'，{2,}', '，', text)
    text = re.sub(r'。{2,}', '。', text)
    text = re.sub(r'\s*([，。：；！？])\s*', r'\1', text)
    return text


def end_sentence(text: str) -> str:
    text = text.strip().rstrip('，、；;,')
    if not text:
        return ''
    return text if text[-1] in '。！？…”' else text + '。'


def ascii_words(text: str) -> set[str]:
    return set(ASCII_WORD.findall(text or ''))
