# Linear Cli

自用的 Linear 命令行工具，由于官方没有提供 CLI，第三方接口也可能随时改变，所以自己制作一个薄 CLI 用于本地操作 Linear。

所有命令默认在 stdout 输出单行 JSON（供 Agent 与脚本消费）；加 `--pretty` 才输出人类可读格式。

## 登录

先用个人 API key 登录，key 会被写入配置文件：

```console
$ linear login --api-key lin_api_xxx
{"viewer": {"id": "...", "name": "Name", "email": "name@example.com"}, "workspace": {"id": "...", "name": "Workspace", "url": "https://linear.app/workspace"}}
```

## 创建 issue

`--team` 传 Team 缩写（如 TES），`--title`、`--body` 必填。返回标识与网页 URL：

```console
$ linear issue create --team TES --title "标题" --body "正文"
{"identifier": "TES-123", "url": "https://linear.app/workspace/issue/TES-123"}

$ linear issue create --team TES --title "标题" --body "正文" --pretty
TES-123 https://linear.app/workspace/issue/TES-123
```

`--body` 原样写入 Linear description，不做任何裁剪、改写或规范化。

## 查看 issue

`view` 只需标识，无需 Team 参数：

```console
$ linear issue view TES-123
{"id": "258773fc-...", "identifier": "TES-123", "url": "https://linear.app/workspace/issue/TES-123", "title": "标题", "description": "正文", "branchName": "name/tes-123-标题", "state": {"id": "...", "name": "In Progress", "type": "started"}, "priority": 2, "priorityLabel": "High", "estimate": null, "assignee": {"id": "...", "name": "Name"}, "createdBy": {"id": "...", "name": "Name"}, "team": {"id": "...", "key": "TES", "name": "Test"}, "labels": [], "project": null, "parentId": null, "createdAt": "2026-08-18T00:00:00.000Z", "updatedAt": "2026-08-18T00:00:00.000Z", "archivedAt": null, "completedAt": null, "startedAt": null, "canceledAt": null, "dueDate": null}

$ linear issue view TES-123 --pretty
TES-123 标题
正文
```

## 列出 issue

`list` 拉取工作区 issue，默认 50 条，输出 JSON 数组（每项为 view 字段集的子集）：

```console
$ linear issue list --limit 10
[{"identifier": "TES-123", "title": "标题", "url": "https://linear.app/...", "state": {"name": "In Progress", "type": "started"}, "priority": 2, "assignee": {"name": "Name"}, "updatedAt": "2026-08-18T00:00:00.000Z"}, ...]
```

`--pretty` 以表格渲染。

支持的过滤 flag（可组合，AND 语义）：

```console
$ linear issue list --team TES --state "In Progress" --assignee me --updated-at=-P1D
$ linear issue list --query "关键词" --order-by createdAt --limit 10
```

| flag | 取值 |
|------|------|
| `--team` | Team 缩写、名称或 UUID |
| `--state` | 状态名称、类型（如 started/backlog）或 UUID |
| `--assignee` | 负责人名称、邮箱、UUID 或 `me` |
| `--label` / `--project` / `--cycle` | 标签 / 项目（名称、slug 或 UUID）/ Cycle（编号、名称或 UUID） |
| `--query` | 关键词，搜索标题与正文 |
| `--created-at` / `--updated-at` | 时间下界：ISO-8601 日期或 `-P1D` 类时长（负前缀值需用 `--created-at=-P1D` 形式） |
| `--order-by` | `updatedAt`（默认）或 `createdAt` |
| `--include-archived` | 默认不含归档，置位才包含 |

## 更新 issue

`update` 只传要改的字段，未传的字段不动；名称类取值（状态/负责人/标签/项目/Cycle）在写入前解析为 UUID，解析不到则确定性报错（`not_found`）。输出更新后的 issue（字段集同 view）：

```console
$ linear issue update TES-123 --state "In Progress" --priority 2
{"id": "...", "identifier": "TES-123", ..., "state": {"name": "In Progress", ...}, ...}

$ linear issue update TES-123 --title "新标题" --assignee me --label bug --due-date 2026-12-31
```

| flag | 说明 |
|------|------|
| `--title` / `--body` | 新标题 / 新正文（正文逐字透传） |
| `--state` | 状态名称、类型（如 started）或 UUID |
| `--priority` | 0=None，1=Urgent，2=High，3=Medium，4=Low |
| `--assignee` | 负责人名称、邮箱、UUID 或 `me` |
| `--label` | 贴一个标签（名称或 UUID），不影响已有标签；尚无该标签时先 `linear label create` |
| `--project` / `--cycle` | 项目名称或 UUID / Cycle 编号、名称或 UUID |
| `--due-date` | 截止日期（yyyy-mm-dd） |

## 评论 issue

`comment` 子命令组用于查看与汇报进度：

```console
$ linear issue comment add TES-123 --body "进度汇报"
{"id": "2a2ced62-...", "url": "https://linear.app/.../issue/TES-123#comment-2a2ced62"}

$ linear issue comment list TES-123
[{"id": "...", "body": "进度汇报", "user": {"id": "...", "name": "Name"}, "createdAt": "2026-08-18T00:00:00.000Z", "updatedAt": "..."}]

$ linear issue comment delete 2a2ced62-...
{"id": "2a2ced62-...", "deleted": true}
```

`add` 的 `--body` 逐字透传（同 create 契约）；`--parent` 传父评论 UUID 即为回复（UUID 从 `comment list` 获得；注意回复仍需指向 issue，二者同时生效）；`delete` 按评论 UUID 删除，用于收回发错的汇报。

## 查询层

核心层命令取值来源（team 缩写、状态名、负责人、标签、项目、Cycle 等）各一条 list：

```console
$ linear team list
[{"id": "...", "key": "TES", "name": "Test"}]

$ linear user list
[{"id": "...", "name": "Name", "displayName": "name", "email": "name@example.com", "active": true}]

$ linear status list --team TES
[{"id": "...", "name": "Todo", "type": "unstarted", "position": 1.0}, ...]

$ linear label list --team TES
[{"id": "...", "name": "Bug", "color": "#EB5757"}, ...]

$ linear project list
[{"id": "...", "name": "dotfiles", "state": "started", "url": "https://linear.app/..."}]

$ linear cycle list --team TES
[{"id": "...", "number": 3, "name": "Cycle 3", "startsAt": "...", "endsAt": "..."}]
```

- `status list` / `cycle list` 的 `--team` 缺省时列出全部 team 的条目拼接；`--team` 取值为缩写或 UUID，解析不到确定性报错。
- `label list --team` 输出该 team 可用的标签全集（workspace 级 + 该 team 的）。
- `label create` 供 `issue update --label` 贴尚不存在的标签：

```console
$ linear label create --team TES --name "release-blocker" --color "#EB5757"
{"id": "...", "name": "release-blocker"}
```

## 配置

配置文件路径按以下优先级解析（全平台统一）：

1. `LINEAR_CONFIG_PATH` 环境变量（最高优先，用于测试隔离）
2. `$XDG_CONFIG_HOME/linear-cli/config.toml`
3. `~/.config/linear-cli/config.toml`（最终回落）

未登录时执行 `create`/`view` 会提示先运行 `linear login`。

## 开发

```console
$ uv run pytest    # 运行测试；真实 API 测试需设置 LINEAR_API_KEY，缺失时自动 skip
```
