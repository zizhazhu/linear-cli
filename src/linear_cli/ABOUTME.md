# linear_cli/

项目唯一的顶层 Python 包，所有业务代码放在这里。

## 布局约定

- CLI 入口在 `app.py`（typer app），`__init__.py` 导出 `app` 与 `main`，
  `__main__.py` 支持 `python -m linear_cli`。
- 子命令按领域拆模块（如 `issue.py`、`project.py`），在 `app.py` 中用
  `app.add_typer(...)` 挂载。
- 与 Linear API 交互的逻辑（GraphQL query/mutation + httpx）放 `api.py` 或
  按领域拆分，与 CLI 层解耦。

## 内容

| 条目 | 说明 |
|------|------|
| `app.py` | typer app 定义与入口函数 `main`；在此挂载各子命令 |
| `api.py` | Linear GraphQL 客户端（query/mutation + httpx），含 issue 的 create/view/list（含 filter 组装）/update（含名称→UUID 客户端解析）/comment/archive 操作，及 teams/states/users/labels/projects/cycles 查询与 label create |
| `config.py` | 配置路径解析（`LINEAR_CONFIG_PATH` → XDG → `~/.config`）、凭据读写、凭据来源解析（环境变量 → `.env` → 配置文件；`.env` 只读不注入环境变量） |
| `output.py` | 成功路径 stdout 格式化：默认 TOON（`toon-format` encode），`--format json` 为单行 JSON 兼容锚点，`--format yaml` 对多行字符串用 block scalar；错误路径不接入 |
| `errors.py` | 结构化 JSON 错误信封：所有命令的失败统一为 stderr 单行 JSON `{"error": {"type": ...}}`（type ∈ auth / not_found / graphql / http）+ 退出码 1；`require_api_key` 为各命令共用的凭据解析入口 |
| `login.py` | `login` 命令：验证 API key 并保存凭据 |
| `guide.py` | `guide` 命令：面向 Agent 的英文使用指南（静态文本，不触网、不需要凭据） |
| `query.py` | 查询层命令组：`team/user/status/label/project/cycle` 各一条 `list`（status/label/cycle 可选 `--team`）与 `label create` |
| `issue.py` | `issue` 命令组：`create`（`--team`/`--title`/`--body`）、`view`（标识）、`list`（`--limit` 默认 50，filters：team/state/assignee/label/project/cycle/query/created-at/updated-at/order-by/include-archived）、`update`（部分更新，字段同 list 的名称类取值）与 `comment` 子组（list/add/delete） |
| `__main__.py` | 支持 `python -m linear_cli` 执行 |
| `__init__.py` | 导出 `app`、`main`，控制公开 API |
