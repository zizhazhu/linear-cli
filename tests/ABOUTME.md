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
- **命令层**：用 `typer.testing.CliRunner` 进程内调用，断言退出码 + 输出的
  结构化数据（解析后比较，不比字符串）。
- **输出层**：默认 JSON 是逐字节基线，只在 `test_output.py` 里以字面量快照
  锁定，其余测试一律解析后比较，避免同一处契约散落多份脆弱断言。
- **归一化层**：纯函数，直接单元测试字段形态与「只含 JSON 原生类型」。
- **共享 fixture**（fake API key、样例 GraphQL 响应等）放 `conftest.py`，
  跨命令复用。

## 内容

| 条目 | 说明 |
|------|------|
| `conftest.py` | 共享 fixture：fake API key、样例 GraphQL 响应（viewer/teams/issue/错误）、凭据环境隔离（`LINEAR_CONFIG_PATH` → `tmp_path`、清除 `LINEAR_API_KEY`、chdir 到临时目录使 `.env` 查找落空） |
| `real_api.py` | 真实 API 契约测试的共享设施：自行读取 `.env`（`dotenv_values`，不污染环境变量），`require_real_api_key` 把同一把 key 同时钉进环境变量与配置文件，缺失时 skip；`delete_issue_label` 为标签 round-trip 测试的清理手段，`comment_parent_id` 为评论回复的读回验证手段（均直连 GraphQL，不进生产模块） |
| `test_app.py` | CLI 入口冒烟测试：`--help` 与无参数时的行为 |
| `test_api.py` | API 客户端测试：成功返回 viewer、HTTP 错误抛 `HTTPStatusError`、网络错误原样传播 |
| `test_config.py` | 配置读写纯函数测试：`read_api_key_from_config` 缺文件/缺字段返回 `None`、写入读取回环；`resolve_api_key` 凭据来源优先级（环境变量 → `.env` → 配置文件，全落空抛 `MissingApiKeyError`；`.env` 是显式数据源，解析不注入环境变量） |
| `test_login.py` | `linear login` 命令测试：有效/无效 key、JSON 默认输出、prompt 入口、覆盖已有凭据、配置路径三级优先（`LINEAR_CONFIG_PATH` → XDG → `~/.config` 回落） |
| `test_issue.py` | `issue create/view/list/update/comment` 测试：必填参数、未登录、未知 Team、GraphQL/HTTP 错误输出、list 的 filter/order-by/include-archived 请求构造、update 的部分更新与名称→UUID 客户端解析、comment list/add/delete/回复（--parent）契约（离线）；env 凭据优先于配置文件（离线）；8 条真实 API 测试（create→view round-trip、view 不存在标识、list --limit 1 字段契约、list filters 服务端读回一致、update 全字段 round-trip、comment add→list→delete round-trip、comment delete 不存在 UUID 错误结构、comment 回复挂载读回）凭据由 `real_api.py` 统一注入，缺失时 skip |
| `test_query.py` | 查询层命令测试：六条 list 的输出字段契约、`--team` 客户端解析与 not_found 短路、label create 的 input 构造（离线）；7 条真实 API 测试（各命令一条字段契约 + label create→list 读回 round-trip，标签清理用 `real_api.delete_issue_label`） |
| `test_normalize.py` | 归一化层纯函数测试：15 条数据输出命令的产物只含 JSON 原生类型（精确类型递归校验，挡住 str 子类与 tuple）、做变换的几条（login/created_issue/issue/created_comment/deleted_comment/label_list）逐一断言字段形态、其余为节点集直通且顶层容器为新对象（嵌套节点仍与响应共享，见 `normalize.py` 模块说明） |
| `test_output.py` | 输出层测试：15 条数据输出命令 × 默认 JSON 的字面量快照（逐字节基线，只许新增不许改）、同批命令 `-o yaml` 与 JSON 视图数据等价、`--pretty` 已不被接受（退出码 2）、`-o` 非法取值走 usage 错误而非信封、执行层错误信封不受 `-o` 影响 |
