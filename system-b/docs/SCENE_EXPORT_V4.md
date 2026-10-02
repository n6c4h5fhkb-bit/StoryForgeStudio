# SceneExport v4

System A 导出、System B 导入的文件保持：

```json
{
  "format": "SceneExport-v1",
  "schemaVersion": 4,
  "source": {},
  "analysisCoverage": {},
  "storyDocument": {},
  "scenes": [],
  "knowledgeSnapshot": {},
  "dramaticFunctions": [],
  "evidenceSnapshot": {},
  "versionFingerprint": ""
}
```

`source` 保存原创/小说来源、原文指纹、章节定位和实际阅读范围；`analysisCoverage` 区分已载入、已分析和已用于改编；`storyDocument` 保存实体、初始状态、事件、对白、故事顺序和播放顺序；`scenes` 保存稳定场次、正文块和对白 ID；其余字段保存人物/观众知识、戏剧作用、来源证据快照和整个采用版本的指纹。

B 继续读取 schema 1–3。旧文件导入新制作流程时按缺失字段生成连续性补全提示；缺失信息只阻塞实际依赖它的任务。v4 导入后，B 的电影、剧集与短剧拍摄版分别保存，并记录所用 A 版本与来源映射。
