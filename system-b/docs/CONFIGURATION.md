# 配置说明

新增 `codex_cli` 调用方式，无需在平台填写 API Key。会话持续复用、登录诊断及计费边界见 [Codex CLI 接入](CODEX_CLI_2026_09_28.md)。下面的单价和 API 输出上限仅适用于 API 连接。

## 语言模型

优先在界面“设置→语言模型”填写。默认 `demo` 不联网。JSON 模式可在 `json_object`、`json_schema`、`none` 中选择：最后一种仅关闭协议的 response_format，仍会在应用端做 JSON/schema 校验。并非所有兼容服务都支持相同 response_format，遇到 HTTP 400 时按服务文档调整。

API 基础地址按协议填写到 `/v1` 或 `/v1beta`，不要重复填写 `/chat/completions`。示例文件只提供协议形状，不预设当前可用模型名和价格。每次模型调用记录输入、输出、schema、token、成本和错误；没有有效配置时明确报错，不自动回退成演示。

单价单位统一为 USD / 每百万 token。免费本地模型填写 0 并勾选“已确认单价”。系统记录模型与媒体费用，并发任务先登记在途费用、再结算；不设置项目累计预算上限，旧配置中的预算字段不再生效。模型返回错误 JSON 仍记录已经发生的 usage。供应商不可见的额外费用需要对账，本地记录不替代服务商账单。

“高级配置”中的 `models` 可以按角色覆盖全局配置，例如：

```json
{
  "models": {
    "structure": {"model": "YOUR-STRONG-MODEL"},
    "script": {"model": "YOUR-MID-MODEL"},
    "validator": {"model": "YOUR-CHECKER-MODEL", "temperature": 0.1},
    "vision": {"model": "YOUR-VLM"}
  }
}
```

A 使用 structure / story / script / validator / vision / intent。B 使用 normalizer / assets / direction / vision。每个角色可覆盖 provider、baseUrl、apiKey、maxTokens 和单价。不要把 provider 的模型名错误地填为 Agent CLI 名称。

## 媒体

`manual`：只导入自己已有的图片和视频，不会调用生成服务。

`demo`：生成带明确英文测试标识的图和测试视频，仅用于校验工程链路。

`dreamina`：调用本机已登录的 Dreamina CLI。默认图片 `5.0 / 2k`，视频 `seedance2.0fast / 720p`，会在每次执行前读取当前 CLI 子命令帮助并核对能力。设置中可填写 `session`；需要自定义命令路径时，在媒体高级字段设置 `command`。

Dreamina 视频模型支持 `seedance2.0`、`seedance2.0fast`、`seedance2.0_vip`、`seedance2.0fast_vip`、`seedance2.0mini` 和 `seedance2.5`。Fast/mini/普通 2.0 只接受 720p；2.0 VIP 还支持 1080p/4k；2.5 支持 480p/720p/1080p。平台根据实际 CLI 帮助校验时长和参考数量。

提交前会写入执行尝试；拿到 `submit_id` 后立即保存。恢复任务只运行 `query_result --submit_id ...`。如果 CLI 可能已经提交但没有返回可靠 ID，状态记为 `state_unknown`，不会自动重提。下载失败只重试查询/下载。真实生成仍须通过批次费用确认。

`openai`：实现了 `/images/generations` 和 `/images/edits`。有参考图时必须启用 `useEdits`，不允许悄悄丢掉参考图。具体模型是否支持这些接口由供应商决定。尺寸、扩展参数可放 `size` / `extraBody`。

`generic`：已有 HTTP 适配器支持创建任务、上传参考素材、轮询任务、下载 URL 或 Base64。不是只有接口名；实际请求代码在 tools 中。**但没有通用的 Seedance 网页账户接口**。请使用自己获授权的服务提供的 API 文档配置路径与响应字段，或直接导入网页生成的素材。

`comfyui`：导入“API 格式”的 workflow JSON，替换明确的占位符。支持 `/prompt`、`/history`、`/view` 和参考图上传。模型权重与自定义节点需要在你自己的 ComfyUI 中已安装；不随应用下载大模型。

### Generic HTTP 示例

参见 `examples/settings.media-generic.json`。其中路径 **是协议示例而不是某家厂商的真实接口**。`resultPath` / `jobIdPath` / `statusPath` 使用点路径，例如 `data.id`、`data.output.url`。不需要异步的接口删除 pollPath，直接解析 resultPath。

可用占位符：`{{prompt}}`、`{{negativePrompt}}`、`{{model}}`、`{{seed}}`、`{{width}}`、`{{height}}`、`{{duration}}`、`{{references}}`、`{{firstFrame}}`、`{{referenceVideo}}`。整值占位符保留数字/数组类型，不全部变成字符串。

配置 uploadPath 时上传本地参考媒体换 URL，否则参考图/视频可按 data URI 传递。API 不接受 data URI 时必须配 uploadPath。存在参考媒体而 bodyTemplate 不引用相应变量时，程序报错而不是退化为文字生成。

### ComfyUI 示例

参见 `examples/settings.comfyui.json`。替换工作流中的节点编号及已有 checkpoint；`{{reference0}}`、`{{reference1}}` 对应上传后图片名，可用于 LoadImage 节点。图片参考工作流与视频延长工作流不是一回事。未配置视频路径映射的 ComfyUI 不应声明 extension / referenceVideo 能力，强依赖视频可改用通用 HTTP 服务。

### 图像与视频分开

System B 的 `media` 是默认配置。需要不同服务时，在高级配置增加 `mediaImages` 和 `mediaVideos` 覆盖，示例 `settings.split-media.json`。图片、资产图、视频分别读取相应配置；改变视频服务不会改变图像服务。

## 制作包、声音与粗剪兼容

当前主交付是“独立制作包 ZIP”。它包含采用媒体原文件、采用区间、镜头顺序、对白与声音提示、素材对应、来源映射、参考职责和版本清单；配音、字幕和最终剪辑在外部软件完成。

旧 B6 继续保留兼容和粗剪用途：可导入 WAV/MP3/M4A/OGG 作为对白、VO、环境声、音乐、音效，编辑进入点、音源截取起点、时长、音量和淡入淡出，也可保留视频原声、定义静默区间并编辑/导入 SRT。

输出 MP4（H.264/AAC）、SRT、WebVTT 和通用 EDL JSON。MP4 包含可选字幕轨；浏览器预览用 WebVTT。EDL 是本系统可追溯的编辑计划，不是 Premiere / Resolve / Final Cut 的原生工程文件。

`imageio-ffmpeg` 提供可用 FFmpeg；有系统 FFmpeg/FFprobe 优先使用。没有 FFprobe 时以 FFmpeg 读取轨道作保守回退。也可在设置里填写绝对路径 `ffmpeg` / `ffprobe`。

本版不捆绑配音、歌曲或拟音生成模型。兼容装配器使用你上传或视频自带的声音；没有声音会明确提示静音预演，不假称已经配乐。

## 自动检测

免费基础检查包括解码、画幅、空白图、时长、亮度突跳。可选 OpenCV 做正脸数量初筛，它不等价于角色身份识别。

精细手脸异常、身份 embedding、文字崩坏和光流/时序身份检查通过 `gatePlugins` 对接专用模型。未配置时状态是 unknown，人工必须复核。VLM 只检查 informationPayload 的是非，不代替所有专用模型。

检测器接收 multipart `media` 文件和 JSON 字符串 `context`，返回：

```json
{"checks":[{"name":"identity","stage":1,"state":"review","message":"需要复核","details":{}}]}
```

有效状态为 pass / fail / review / unknown。API 插件须部署在你信任的环境，承担参考资产匹配能力；没有模型就不能声称完成语义检测。

## 常见报错

| 现象 | 处理 |
|---|---|
| 生成被 price_required 阻止 | 确认服务商价格；免费填 0 后勾选。 |
| 场景时长与风格区间无交集 | 调整该场时长或风格范围；代码不静默违背风格。 |
| 主资产/风格未锁定 | 在 B1/B2 做人工定稿，不仅是保存。 |
| 视频缺少关键帧 | 先生成或上传并终选本镜关键帧。 |
| unsupported_capability | 服务没有声明/实现该强依赖能力，换服务或改镜间关系。 |
| broken / locked 冲突 | 审查上游差异后人工仲裁，不要删除数据库强行跳过。 |
| 服务已重启 interrupted | 核对远端任务状态，手动重试，避免重复付费。 |
| 界面打开空白 | 用 launcher 启动，不直接双击 static/index.html；看终端错误。 |
| pip 安装失败 | 设置本机 pip 网络/镜像后重启，不删除 data。 |
