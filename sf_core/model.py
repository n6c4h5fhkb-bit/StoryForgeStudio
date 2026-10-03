"""Plain data objects for an authored project. Parsers fill them; nothing here does I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

KIND_NAMES = {
    'character': ('人物', '角色', 'character', 'characters'),
    'crowd': ('群演', '群众', '群像', 'crowd', 'extras'),
    'location': ('场景', '地点', 'location', 'locations'),
    'prop': ('道具', '物件', 'prop', 'props'),
}
TAGS = ('钩子', '爽点', '反转', '冲突', '打脸', '高光', '伏笔', '卡点', '高潮', '悬念')
TURN_TAGS = ('爽点', '反转', '冲突', '打脸', '高潮', '高光')


@dataclass
class Issue:
    level: str          # error | warning | info
    code: str
    where: str
    message: str

    def as_dict(self):
        return {'level': self.level, 'code': self.code, 'where': self.where, 'message': self.message}


@dataclass
class Entity:
    name: str
    kind: str                                   # character | crowd | location | prop
    aliases: list[str] = field(default_factory=list)
    identity: str = ''                          # 身份 / 外观 / 布局
    looks: dict[str, str] = field(default_factory=dict)   # 造型 name -> description; first is default
    states: dict[str, str] = field(default_factory=dict)  # 状态（名）: prop or location variants
    marks: str = ''
    voice: str = ''
    count: int | None = None
    holder: str = ''                            # props: initial holder (a character name)
    place: str = ''                             # props: initial place
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def default_look(self) -> str | None:
        return next(iter(self.looks), None)

    def names(self) -> list[str]:
        return [self.name, *self.aliases]


@dataclass
class Series:
    title: str = ''
    format_name: str = '横屏剧集'
    model: str = 'seedance-2.0'
    style: str = ''
    face: str = '待测试'
    rate: float | None = None
    audio: str = '模型同期声'
    subtitles: str = '无'
    music: str = '无'
    narration: str = ''
    content: str = ''
    extra: dict[str, str] = field(default_factory=dict)
    fmt: dict = field(default_factory=dict)      # resolved format profile
    cap: dict = field(default_factory=dict)      # resolved capability profile

    @property
    def speech_rate(self) -> float:
        return float(self.rate or self.fmt.get('speech_rate', 5.0))

    @property
    def narration_on(self) -> bool:
        if self.narration:
            return self.narration not in ('无', '否', '关', 'off', 'no')
        return bool(self.fmt.get('narration'))

    @property
    def native_audio(self) -> bool:
        return '后期' not in self.audio and '配音' not in self.audio and bool(self.cap.get('native_audio', True))


@dataclass
class Line:
    """One meaningful script line, in file order."""
    kind: str            # action | speech | inner | narration | sfx | state | jump | note
    text: str
    speaker: str = ''
    paren: str = ''
    offscreen: bool = False
    anchor: str = ''     # Lnnn, assigned by `sf ids`
    lineno: int = 0
    scene: str = ''


@dataclass
class Scene:
    id: str
    location: str = ''
    time: str = ''
    day: str = ''
    heading: str = ''
    lines: list[Line] = field(default_factory=list)
    lineno: int = 0


@dataclass
class Shot:
    id: str
    scene: str
    size: str = ''
    who: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    action: str = ''
    tags: list[str] = field(default_factory=list)
    duration: float | None = None
    move: str = ''
    angle: str = ''
    transition: str = ''     # '' | 省略 | 重置
    stage: str = ''
    note: str = ''
    lineno: int = 0


@dataclass
class ShotScene:
    id: str
    defaults: dict[str, str] = field(default_factory=dict)
    shots: list[Shot] = field(default_factory=list)


@dataclass
class Episode:
    id: str
    title: str = ''
    script_path: Path | None = None
    shots_path: Path | None = None
    scenes: list[Scene] = field(default_factory=list)
    shot_scenes: list[ShotScene] = field(default_factory=list)

    def all_shots(self) -> list[Shot]:
        return [shot for scene in self.shot_scenes for shot in scene.shots]

    def line_index(self) -> dict[str, Line]:
        return {line.anchor: line for scene in self.scenes for line in scene.lines if line.anchor}

    def scene(self, scene_id: str) -> Scene | None:
        return next((scene for scene in self.scenes if scene.id == scene_id), None)


@dataclass
class OutlineEpisode:
    id: str
    title: str = ''
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class Project:
    root: Path
    series: Series
    entities: dict[str, Entity]
    outline: list[OutlineEpisode]
    episodes: list[Episode]
    issues: list[Issue] = field(default_factory=list)

    def lookup(self, name: str) -> Entity | None:
        """Resolve a name or alias to its entity."""
        name = (name or '').strip()
        if name in self.entities:
            return self.entities[name]
        for entity in self.entities.values():
            if name in entity.aliases:
                return entity
        return None

    def episode(self, episode_id: str) -> Episode | None:
        return next((episode for episode in self.episodes if episode.id.upper() == episode_id.upper()), None)


@dataclass
class ShotPlan:
    """A shot with everything derived for it."""
    shot: Shot
    lines: list[Line]
    duration: float
    start: float = 0.0                       # position on the episode's edit timeline
    world_start: dict = field(default_factory=dict)
    world_end: dict = field(default_factory=dict)
    jump: str = ''                           # 【时间跳转】 text just before this shot


@dataclass
class Reference:
    slot: int
    entity: str
    kind: str
    variant: str
    file: str = ''
    sha256: str = ''


@dataclass
class UnitPlan:
    id: str
    scene: Scene
    defaults: dict
    shots: list[ShotPlan]
    gen_seconds: int
    references: list[Reference] = field(default_factory=list)
    text_only: list[str] = field(default_factory=list)
    segments: list[tuple[int, int]] = field(default_factory=list)
    prompt: str = ''
    issues: list[Issue] = field(default_factory=list)

    @property
    def edit_seconds(self) -> float:
        return round(sum(plan.duration for plan in self.shots), 1)
