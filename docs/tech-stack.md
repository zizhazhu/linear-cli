# 技术方案

## 语言选择：Python

### 决策

使用 Python 实现。

### 理由

- Linear API 本质是 GraphQL over HTTP，手写少量 query/mutation + `httpx` 发请求即可，
  不依赖官方 TypeScript SDK。
- README 定位为"薄 CLI"，手写 GraphQL 直连官方 API 符合"不依赖第三方封装"的哲学。
- Agent 工作流场景下语言无关——Agent 通过 shell 调 CLI，只关心命令接口和输出格式。
- 自用工具无需分发，`uv tool install` 一条命令即可全局安装。
- 维护者熟悉 Python，迭代快、维护成本低。

### 短板与影响

- 启动延迟 ~50-150ms：对交互式 CLI 和 Agent 调用无感。
- 无官方 SDK 类型提示：查询字段固定，影响有限；需要时用 `dataclass` / `pydantic` 建模。

## 技术栈

### 包管理：uv

项目管理 + `uv tool install` 全局安装。

### CLI 框架：typer

基于 `click` 的封装，底层就是 click。选择 typer 的理由：

- **类型注解驱动**：从函数签名的 type hints 推导参数类型、是否必填、是否 flag，
  不用像 click 那样重复声明装饰器。
- **子命令组织直观**：`app.add_typer(issue_app, name="issue")` 天然支持
  `linear issue list` 这种多级嵌套命令结构。
- **默认集成 rich**：`--help` 输出自动美化。
- **自动补全**：内置生成 shell completion。

不选 click 的原因：click 的装饰器声明风格导致参数与函数签名分离、重复书写；
click 的零依赖优势在这个薄 CLI 中不构成决定性因素。

### HTTP 客户端：httpx

直接 POST 到 `https://api.linear.app/graphql`。

### 终端渲染：rich

负责展示层，不影响业务逻辑。核心用途：

- **表格**：`rich.table.Table` 渲染 issue 列表（ID、标题、状态、优先级），
  服务"个人任务面板"场景。
- **颜色与样式**：按状态/优先级上色，一眼扫出重点。
- **Markdown 渲染**：Linear issue 描述是 Markdown，`rich.markdown.Markdown`
  可在终端渲染标题、列表、代码块。
- **Spinner**：网络请求时显示 loading 动画。
- **异常美化**：traceback 带语法高亮，调试省事。

**与 Agent 模式的配合**：`--json` 时绕过 rich 输出纯 JSON；rich 自动检测 TTY，
管道/重定向时自动去掉颜色控制符，不污染 Agent 读到的文本。

### 认证

Personal API Key，从环境变量 `LINEAR_API_KEY` 或配置文件读取。

配置文件路径按以下优先级解析：

1. `LINEAR_CONFIG_PATH` 环境变量（最高优先，用于测试隔离与临时切换身份）
2. `platformdirs.user_config_path("linear-cli")` 给出的平台标准目录：
   - Linux：`$XDG_CONFIG_HOME/linear-cli`，未设置时回落 `~/.config/linear-cli`
   - Windows：`%APPDATA%\linear-cli`
   - macOS：`~/Library/Application Support/linear-cli`

跨平台差异交给 `platformdirs` 保证（库自带各平台测试），本项目只测试
`LINEAR_CONFIG_PATH` 覆盖层与 Linux 下的 XDG/回落行为。

## 依赖清单

| 包 | 用途 |
|------|------|
| `typer` | CLI 框架（自带 rich 依赖） |
| `httpx` | HTTP 客户端，发送 GraphQL 请求 |
| `rich` | 终端富文本渲染（typer 间接依赖，显式声明便于直接使用） |
| `platformdirs` | 跨平台用户配置目录解析（Linux XDG / Windows APPDATA / macOS） |
