# linear_cli/

项目唯一的顶层 Python 包，所有业务代码放在这里。

## 布局约定

- CLI 入口在 `app.py`（typer app），`__init__.py` 导出 `app` 与 `main`，
  `__main__.py` 支持 `python -m linear_cli`。
- 子命令按领域拆模块（如 `issue.py`、`project.py`），在 `app.py` 中用
  `app.add_typer(...)` 挂载。
- 与 Linear API 交互的逻辑（GraphQL query/mutation + httpx）放 `api.py` 或
  按领域拆分，与 CLI 层解耦。
- 成功输出走两段管线：`normalize.py` 把 API 响应映射为输出数据，`output.py`
  按 `-o/--output` 渲染到 stdout。命令层只交数据，不拼字符串——失败输出的
  对应层是 `errors.py`。

## 内容

| 条目 | 说明 |
|------|------|
| `app.py` | typer app 定义与入口函数 `main`；在此挂载各子命令 |
| `api.py` | Linear GraphQL 客户端（query/mutation + httpx），含 issue 的 create/view/list（含 filter 组装）/update（含名称→UUID 客户端解析）/comment/archive 操作，及 teams/states/users/labels/projects/cycles 查询与 label create |
| `config.py` | 配置路径解析（`LINEAR_CONFIG_PATH` → XDG → `~/.config`）、凭据读写、凭据来源解析（环境变量 → `.env` → 配置文件；`.env` 只读不注入环境变量） |
| `errors.py` | 结构化 JSON 错误信封：执行层失败统一为 stderr 单行 JSON `{"error": {"type": ...}}`（type ∈ auth / not_found / graphql / http）+ 退出码 1；参数用法错误留给 typer（usage 文本 + 退出码 2）；`require_api_key` 为各命令共用的凭据解析入口 |
| `normalize.py` | 归一化层：每条数据输出命令一个函数，把 GraphQL 响应映射为只含 JSON 原生类型的输出数据（view/update 共用 `issue`）；多数命令的选择集即输出契约，归一化为节点集直通 |
| `output.py` | 输出层：`OutputFormat`（json/yaml）与各命令共用的 `-o/--output` 声明 `OutputOption`，`emit` 把归一化数据渲染到 stdout——JSON 单行不转义非 ASCII，YAML 保序、多行文本用块标量 |
| `login.py` | `login` 命令：验证 API key 并保存凭据 |
| `guide.py` | `guide` 命令：面向 Agent 的英文使用指南（静态文本，不触网、不需要凭据） |
| `query.py` | 查询层命令组：`team/user/status/label/project/cycle` 各一条 `list`（status/label/cycle 可选 `--team`）与 `label create` |
| `issue.py` | `issue` 命令组：`create`（`--team`/`--title`/`--body`）、`view`（标识）、`list`（`--limit` 默认 50，filters：team/state/assignee/label/project/cycle/query/created-at/updated-at/order-by/include-archived）、`update`（部分更新，字段同 list 的名称类取值）与 `comment` 子组（list/add/delete） |
| `__main__.py` | 支持 `python -m linear_cli` 执行 |
| `__init__.py` | 导出 `app`、`main`，控制公开 API |
