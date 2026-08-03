# tests/

单元测试目录，使用 pytest。

## 约定

- 测试文件命名 `test_*.py`，与被测模块一一对应。
- 运行方式：`uv run pytest`。

## 测试策略

统一在 HTTP 边界打测试替身，不 mock 项目内部接口：

- **Mock 边界**：所有涉及网络的测试用 `respx` 拦截 `httpx` 请求，返回预制的
  GraphQL JSON 响应；绝不请求真实 Linear API。命令层测试因此是走
  「命令解析 → 客户端 → 响应解析」全链路的小型集成测试。
- **纯函数逻辑**（query 构造、格式化、参数校验等）：直接单元测试，不用任何 mock。
- **客户端层**：用 `respx` 精细覆盖错误路径（401、GraphQL `errors` 字段、超时等）。
- **命令层**：用 `typer.testing.CliRunner` 进程内调用，断言退出码 + `--json`
  输出的结构化数据。
- **渲染层（rich）**：不对渲染结果做字符串断言（脆弱且非业务逻辑），
  只保留「不抛异常」级别的冒烟测试。
- **共享 fixture**（fake API key、样例 GraphQL 响应等）放 `conftest.py`，
  跨命令复用。

## 内容

| 条目 | 说明 |
|------|------|
| `conftest.py` | 共享 fixture：fake API key、样例 GraphQL 响应（viewer/teams/issue/错误）、凭据环境隔离（`LINEAR_CONFIG_PATH` → `tmp_path`、清除 `LINEAR_API_KEY`、chdir 到临时目录使 `.env` 查找落空） |
| `real_api.py` | 真实 API 契约测试的共享设施：自行读取 `.env`（`dotenv_values`，不污染环境变量），`require_real_api_key` 把同一把 key 同时钉进环境变量与配置文件，缺失时 skip |
| `test_app.py` | CLI 入口冒烟测试：`--help` 与无参数时的行为 |
| `test_api.py` | API 客户端测试：成功返回 viewer、HTTP 错误抛 `HTTPStatusError`、网络错误原样传播 |
| `test_config.py` | 配置读写纯函数测试：`load_api_key` 缺文件/缺字段返回 `None`、保存读取回环；`resolve_api_key` 凭据来源优先级（环境变量 → `.env` → 配置文件，全落空抛 `MissingApiKeyError`；`.env` 是显式数据源，解析不注入环境变量） |
| `test_login.py` | `linear login` 命令测试：有效/无效 key、`--json` 输出、prompt 入口、覆盖已有凭据、配置路径三级优先（`LINEAR_CONFIG_PATH` → XDG → `~/.config` 回落） |
| `test_issue.py` | `issue create/view` 测试：必填参数、未登录、未知 Team、GraphQL/HTTP 错误输出；env 凭据优先于配置文件（离线）；2 条真实 API 测试（create→view round-trip、view 不存在标识）凭据由 `real_api.py` 统一注入，缺失时 skip |
