# Runner 配置与验收

默认 Operator 是可信 subprocess，开箱不依赖 Pi/Codex。运行时推理仍为直接 HTTP 模型请求。

## 优先级

单次 UI 下拉指定 > routing.overrides > routing.roles。默认 fallback.enabled=false。Runner 切换不影响相同 renderKey 的缓存。

`examples/routing.yaml` 是路由参考；实际应用读取 data/settings.json 中的 routing，可在“执行器与路由”里修改。YAML 不会被悄悄当作第二真相源。

## 第三方 CLI

1. 在自己的 Docker 镜像里安装并固定 CLI 版本及必要 Python 渲染依赖。可以使用 `Dockerfile.runner` 模板构建。
2. 在 RunnerProfile 配置 image、cmd、argsTemplate、env、超时、并发和保守费用估计。版本不同的 CLI 参数以本机实际帮助为准。
3. 运行界面“12项验收”。结果记录当前配置的 hash；配置变更需要重验。
4. 全通过后再 enabled=true，最后修改路由。启用这个字段本身不会跳过资格检查。

镜像只读，/work 为本次任务可写目录。渲染输入明确列在 task.json；只有授权参考文件会复制进工作区。不要挂载家目录或整个项目库。执行层不会自动读取你的浏览器登录态。

## 本机直连（sandbox.type = host）

不想用 Docker 时，可把 profile 的 `sandbox.type` 写成 `host`，由本机已安装的 CLI 直接执行。

1. `invoke.cmd` 填可执行文件，`argsTemplate` 填参数。Windows 上建议写成 `node` 加 CLI 入口 js 的绝对路径：参数不要经过 `cmd.exe`，`.CMD` / `.BAT` 转发会重写含换行、引号和 `&` 的长提示词。
2. `invoke.env` 可覆盖子进程环境变量；`invoke.prependPath` 是一个目录数组，会加在继承的 PATH 前面（本系统解释器目录始终排在最前，因此 `python` 解析到已装渲染依赖的环境）。agent 的 bash 工具需要有真正的 bash：本机 `bash` 指向 WSL 且没有发行版时，把 Git 的 `bin` 与 `usr\bin` 放进 `prependPath`。不要用 `env.PATH` 复制整份 PATH，那样会在本机 PATH 变化后变成过期快照。
3. 仍然要通过同一份 12 项验收，`enabled` 只能在验收通过后打开；profile 任何字段变化都会让旧验收失效。
4. host 模式**没有操作系统级隔离**：子进程环境被收窄、参数不经过 shell、产物仍校验在授权工作区内，但它以你的用户权限运行，能读到你的用户目录。只对你信任的 CLI 使用。审计分别记录 `runner_selected.mode` 与 `runner.sandbox='host'`。

## 任务与结果

TaskSpec：taskId、role、stage、objective、inputs、tools、workdir、acceptance、limits、reportSchema。工具白名单为 render / ffmpeg / read_task / write_report。渲染时写 normalized report.json，必须记录实际 Prompt。

RunResult：status、artifacts、report、usage、runner。产物路径必须在授权工作区，文件存在、满足大小和扩展名，并生成 SHA256。

12组固定验收：正常2、自愈2、拒绝1、CLI报错2、超时1、预算1、轮次1、越界1、八路并发1。该验收验证执行契约，不保证生成模型的画面质量。

## 费用

dry-run 计入媒体预估与 Runner 单次估计。能读到usage则记录，缺少真实成本时保守估算并标注。外部 Agent 的远端消耗不能被本地 timeout 完全撤销，所以仍需服务商预算上限。
