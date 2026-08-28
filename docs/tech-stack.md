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

### 输出渲染：标准库 json + PyYAML

成功输出只有两个视图，都由同一份归一化数据渲染（见 command-design.md
「全局契约」）：

- **JSON**（默认）：标准库 `json`，单行、不转义非 ASCII，供 Agent 与脚本
  逐行消费、直接喂 jq。
- **YAML**（`-o yaml`）：PyYAML，保持键序，多行文本用块标量——Linear 的
  issue 正文与评论是多行 Markdown，块标量能原样保留空行与缩进，这正是人类
  读输出时最在意的部分。

不做终端富文本渲染（表格、上色、Markdown 渲染）：表格塞不进 Markdown 正文，
且每条命令都要维护一份与 JSON 平行的渲染路径，两者迟早对不上字段。人类可读
性交给 YAML 视图，字段与 JSON 天然一致。真需要表格式界面时，在归一化层之上
另叠一层即可，不必回到 per-command 渲染。

PyYAML 而非 ruamel.yaml：只做单向 dump，不需要保留注释与往返保真。

### 认证

Personal API Key，从环境变量 `LINEAR_API_KEY` 或配置文件读取。

配置文件路径按以下优先级解析（全平台统一，不做平台分支）：

1. `LINEAR_CONFIG_PATH` 环境变量（最高优先，用于测试隔离与临时切换身份）
2. `$XDG_CONFIG_HOME/linear-cli/config.toml`（设了就认）
3. `~/.config/linear-cli/config.toml`（最终回落）

Windows 不走 `%APPDATA%` 的平台惯例：统一 `~/.config` 让多台机器间路径心智
一致，平台分支也整个消失。目录解析仅三行逻辑，手写即可，不引入
platformdirs 一类的库。

## 依赖清单

| 包 | 用途 |
|------|------|
| `typer` | CLI 框架（自带 rich 依赖，用于 `--help` 与 usage 错误的排版） |
| `httpx` | HTTP 客户端，发送 GraphQL 请求 |
| `pyyaml` | `-o yaml` 的渲染 |
| `python-dotenv` | 读 `.env` 里的凭据（只读，不注入环境变量） |
