# 命令设计：从 Linear MCP 推导 CLI 命令面

本文档以官方 Linear MCP（`mcp__linear__*`）为能力清单参照，推导本 CLI 的
命令面，作为后续实现的依据。MCP 定「做什么」，GraphQL API 定「长什么样」。

## 设计原则

### Agent 优先

CLI 的主要调用方是 Agent（经 shell 调用），其次才是人：

- **默认输出 JSON** 到 stdout；`--pretty` 才输出人类可读格式（rich 渲染）。
- **错误是数据结构**：失败时 stderr 输出单行 JSON 错误信封，退出码非 0。
  Agent 读 `type` 字段分支，不做文本匹配。
- `--help` 文本按 tool description 标准写：每个 flag 说清取值来源与格式。

### 错误信封

```json
{"error": {"type": "...", "...": "..."}}
```

| `type` | 触发场景 | 字段 |
|--------|----------|------|
| `auth` | 三优先级都解析不到 API key | `messages`：含 `linear login` 提示 |
| `not_found` | 客户端解析失败（如 Team 缩写不存在） | `messages`：含用户输入原文 |
| `graphql` | 响应含 `errors` | `messages`：`errors[].message` 逐条原文、保序；账号级错误（extensions 命中 AUTHENTICATION/AUTHORIZATION/RATE_LIMIT）另附 `raw`（完整响应正文） |
| `http` | HTTP 非 2xx | `status`：状态码；`raw`：响应正文文本 |

退出码：业务错误 1；参数用法错误由 typer 出 2（不走信封）。

### 命名：三层参照系

| 层 | 跟谁对齐 | 理由 |
|----|----------|------|
| JSON 字段名 | **GraphQL schema**（如 `identifier`、`state.name`） | 真值层，官方文档可查，Agent 凭 Linear API 知识即可读懂 |
| 内部函数名 | **GraphQL 操作名**（如 `fetch_viewer` ↔ `query Viewer`） | 现状即正确，不需改名 |
| 命令动词 | **gh CLI 惯例**（`view`/`list`/`create`/`update`/`comment`） | Agent 训练数据中最熟悉的 issue CLI 接口 |

**不**抄 MCP 的工具名与动词形态。MCP 的 `save_issue`（create/update 合一）
是工具数受限下的省调用设计；CLI 没有词表成本，`create`/`update` 分开更
符合 gh 惯例，也避免入参语义分裂（`--team` 在 create 必填、update 无意义）。

### MCP 的角色与边界

- MCP 是**能力清单与语义参照**：该暴露哪些操作、哪些字段、哪些 filter、
  错误长什么样，开发时调 MCP 实测确认。
- MCP 是 GraphQL API 的**衍生视图**，有真实缺口与漂移：实测发现
  `list_teams` 不返回 `key`、`issue` 的 `id` 被改写为标识符、字段重命名
  （`status` ↔ `state.name`）、不存在的 issue 在 MCP 报 HTTP 400 而
  GraphQL 返回 200 + `errors`。字段与行为真值一律以 GraphQL 为准。
- MCP **不进入测试回路**（OAuth 凭证无法复用于 pytest，在线依赖违反离线
  纪律）；回归网是固化后的合约测试。见 AGENTS.md「功能开发流程」。

## 全局契约

- 认证：Personal API key，三级优先级（env → `.env` → 配置文件），见
  tech-stack.md，本文不重复。
- 所有命令共享输出层：默认 JSON；`--pretty`；错误信封。
- `--json` flag 不复存在（JSON 是默认行为）。

## 命令清单

### 核心层

#### login

MCP 参照：`get_user("me")` + `get_workspace`

```console
$ linear login --api-key lin_api_xxx
```

- 验证 key（`viewer` 查询）→ 写配置文件，流程不变。
- 默认输出 JSON：`viewer{id, name, email}` + `workspace{id, name, url}`
  两个顶层字段——workspace 元信息并入 login，不单设命令。
- `--pretty` 输出 `已登录：Name <email>`。

#### issue view

MCP 参照：`get_issue`

```console
$ linear issue view TES-123
```

输出字段（GraphQL 命名）：

```
id, identifier, title, description, url, branchName,
state { id, name, type }, priority, priorityLabel, estimate,
assignee { id, name } | null, createdBy { id, name },
team { id, key, name }, labels: [name...],
project { id, name } | null, parentId | null,
createdAt, updatedAt, archivedAt, completedAt, startedAt, canceledAt, dueDate
```

- 以 MCP `get_issue` 默认返回为蓝本，砍 SLA 系列与 `triageIntel`（噪音）；
  attachments / relations / stateHistory 属 MCP `include*` 增强项，不进默认集。
- 可空字段原样输出 `null`，不省略。
- 标识不存在：走 `graphql` 错误信封（GraphQL 真值是 200 + `errors`，
  不是 MCP 的 HTTP 400）。

#### issue create

MCP 参照：`save_issue`（create 路径）

```console
$ linear issue create --team TES --title "标题" --body "正文"
```

- 默认输出 JSON：`{"identifier": "...", "url": "..."}`；`--pretty` 输出
  `TES-123 https://...` 单行。
- `--body` 逐字透传，不做任何裁剪/改写/规范化（现有契约，不变）。
- **team key 在客户端解析**为 UUID 后再发 mutation（先查 teams）：写入前
  即可确定性报 `not_found`。这是与 MCP 模糊解析的**有意差异**，不对齐。

#### issue list（新增）

MCP 参照：`list_issues`

```console
$ linear issue list [--team TES] [--state "In Progress"] [--assignee me] ...
```

filters（MCP 入参拍平为 flag）：

```
--team  --state  --assignee (支持 me)  --label  --project  --cycle
--query (搜索标题/正文)  --created-at  --updated-at (ISO-8601 或 -P1D 类时长)
--limit (默认 50)  --order-by (createdAt|updatedAt)  --include-archived
```

- `--include-archived` 默认 **false**，与 MCP 默认 true 相反：个人任务
  面板场景下 archived 是噪音。
- 列表项字段为 view 字段集的子集：
  `identifier, title, state{name,type}, priority, assignee{name}, updatedAt, url`。
- 输出为 JSON 数组；分页 cursor 先不暴露，超出 `--limit` 时截断即可。

#### issue update（新增）

MCP 参照：`save_issue`（update 路径）

```console
$ linear issue update TES-123 [--title T] [--body B] [--state S] ...
```

flags：`--title, --body, --state, --priority, --assignee, --label,
--project, --cycle, --due-date`。

- 只传要改的字段；未传的字段不动（部分更新语义）。
- `--state` / `--assignee` / `--label` 等的取值经查询层命令在客户端解析为
  UUID（与 create 的 team 解析同一原则：写入前确定性报 `not_found`）。
- 默认输出更新后的 issue JSON（字段集同 view）。

#### issue comment list / add / delete（新增）

MCP 参照：`list_comments` / `save_comment` / `delete_comment`

```console
$ linear issue comment list TES-123
$ linear issue comment add TES-123 --body "进度汇报"
$ linear issue comment delete <comment-id>
```

- `list` 输出评论数组：`id, body, user{id,name}, createdAt, updatedAt`。
- `add` 的 `--body` 逐字透传（同 create 契约）；默认输出
  `{"id": "...", "url": "..."}`。
- `delete` 按评论 UUID 删除（UUID 从 `comment list` 获得）；输出
  `{"id": "...", "deleted": true}`。覆盖 Agent 发错汇报需收回的场景。
- 这是 Agent 汇报进度的出口，优先级高于查询层。

### 查询层

核心层命令的取值来源（team key、state 名、assignee、label 等），各一条
list 即可，不做 get：

| 命令 | MCP 参照 | 输出字段 |
|------|----------|----------|
| `team list` | `list_teams` | `id, key, name`（**必须含 `key`**——MCP 返回缺此字段，以 GraphQL 为准） |
| `user list` | `list_users` | `id, name, displayName, email, active` |
| `status list` | `list_issue_statuses` | `id, name, type, position`（按 team 分组可选 `--team`） |
| `label list` | `list_issue_labels` | `id, name, color`（可选 `--team`） |
| `label create` | `create_issue_label` | `id, name`（`--team --name [--color]`；供 `issue update --label` 贴尚不存在的标签） |
| `project list` | `list_projects` | `id, name, state, url` |
| `cycle list` | `list_cycles` | `id, number, name, startsAt, endsAt`（可选 `--team`） |

## 明确不做

MCP 共 58 个工具，命令面覆盖 14 个（issue 3 + comment 3 + 查询元数据 7 +
workspace 并入 login）；核心工作流「看面板 → 建/改 issue → 汇报进度」的
读写路径 100% 覆盖。以下按域说明砍掉的对象与原因；真需要时单独立项，
不预先进命令面（YAGNI）。

### 团队协作/管理面向的对象（约 24 个工具）

documents、initiatives、releases、milestones、status updates、attachments
全套（含各自的 get/list/save/delete 与 initiative labels、release
notes/pipelines、project labels）：

- 这些对象服务多人协作流程：documents 是团队知识库；initiatives /
  milestones / releases 是项目管理者的组合层级与发版流程；status updates
  依附于 project/initiative 的进度通报；attachments 面向富媒体协作。
  单人自用 + Agent 工作流不触及。
- attachments 另有实现成本因素：上传是三段式链路（prepare upload → 直传
  对象存储 → 建附件），而 Agent 在 issue 正文贴 URL 即达同样效果。
- `list_project_labels` 是项目级标签，与 issue 标签是两套；项目域本身不
  做管理操作，其标签随之不做。

### Agent 专属（4 个）

`get_agent_skill` / `list_agent_skills` / `search_documentation` /
`extract_images`：前两者面向 MCP host 内的 Agent 技能配置；
`search_documentation` 搜索的是 Linear 产品自身的使用文档，人用浏览器查
更合适；`extract_images` 服务多模态 Agent 的图片理解，CLI 的文本流
不需要。

### diff / review 系列（8 个）

`get_diff` / `list_diffs` / `merge_diff` / `get_diff_threads` /
`save_diff_comment` / `resolve_diff_thread` / `submit_diff_review` /
`delete_diff_comment`：Linear 的代码审查对象（把 diff 挂上 issue、审查
讨论串、提交审查结论）。本工作区的代码审查走 GitHub PR（现有 issue 的
attachment 即 PR 链接），Linear 侧只做状态跟踪，不做审查。

### 依附于不做域的 delete / create

`delete_attachment` / `delete_status_update` / `create_initiative_label`
等随其所属域一并排除。例外：`delete_comment` 与 `create_issue_label`
属于核心工作流，已纳入命令面（覆盖率清点后补入）。

### save 合并动词与衍生字段

- **不抄 `save_issue` 的 create/update 合并语义**：见「命名：三层参照系」。
- **不引入 MCP 衍生便利字段**：SLA 系列、`triageIntel`；`gitBranchName`
  用 GraphQL 原生 `branchName` 表达。

## 实现顺序

按契约面推进，每域遵循「MCP 探查 → 红灯测试 commit → 绿灯实现 commit」：

1. ~~错误信封契约~~（红灯已落：commit `6584983`）
2. `issue view`：字段扩展 + JSON-first + `--pretty`
3. `issue create` 与 `login`：输出翻转（小，合并推进）
4. `issue list`
5. `issue update`（依赖查询层的取值解析，可视需要提前做 `team/status/
   user/label list` 中的对应条目）
6. `issue comment list/add/delete`
7. 查询层其余条目（含 `label create`）

## 与合约点清单的关系

每条命令实现时，其真实 API 合约点清单按 AGENTS.md 规约写进对应 Linear
issue（打在 LIC team），文档不重复维护合约点。本文档只回答「有哪些命令、
每条命令的形态与语义」。
