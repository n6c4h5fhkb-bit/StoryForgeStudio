"""Escaped, portable reading fragments for adopted creative intent and direction."""
from html import escape


def _text(value):
    return escape(str(value or '')).replace('\n', '<br>')


def _line(label, value):
    return f'<p><strong>{_text(label)}：</strong>{_text(value)}</p>' if value else ''


def intent_html(intent, names=None):
    if not isinstance(intent, dict):
        return ''
    names = names or {}
    parts = [_line('情节变化', intent.get('dramaticChange'))]
    for actor in intent.get('characters', []):
        parts.append(_line(names.get(actor.get('entityId'), '人物目的'), actor.get('goal')))
        parts.append(_line('阻碍', actor.get('obstacle')))
    for key, label in (('mustUnderstand', '本场要理解'), ('withheld', '暂缓揭示'), ('openToInterpretation', '保留解释空间')):
        for item in intent.get('audience', {}).get(key, []):
            parts.append(_line(label, item.get('information')))
            if key == 'withheld': parts.append(_line('暂缓依据', item.get('reason')))
    return '<details><summary>本场故事意图</summary>'+''.join(parts)+'</details>'


def direction_html(plan):
    if not isinstance(plan, dict) or not plan:
        return ''
    summary = ''.join('<p>'+_text(value)+'</p>' for value in plan.get('summary', [])[:3])
    details = ''.join(_line(label, plan.get(key)) for label, key in (
        ('观看重点', 'focus'), ('表演过程', 'performance'), ('空间组织', 'space'), ('动作与剪辑节奏', 'rhythm')))
    return summary+'<details><summary>本场拍法依据</summary>'+details+'</details>'


def shot_html(shot):
    cut = shot.get('cutPoint') or {}; camera = shot.get('cameraCue') or {}
    beats = shot.get('performanceBeats') or []
    progression = '<ol>'+''.join('<li>'+(_text(beat.get('trigger'))+' → ' if beat.get('trigger') else '')+
        _text(beat.get('action'))+('；结束于：'+_text(beat['endCue']) if beat.get('endCue') else '')+
        _line('表演依据', beat.get('reason'))+'</li>' for beat in beats)+'</ol>' if beats else ''
    details = progression+''.join(_line(label, camera.get(key)) for label, key in (
        ('摄影机开始', 'start'), ('摄影机跟随', 'follow'), ('摄影机停止', 'end'), ('运镜依据', 'reason')))+_line('切镜依据', cut.get('reason'))
    return _line('切点', cut.get('cue'))+('<details><summary>表演与切镜依据</summary>'+details+'</details>' if details else '')
