# src/

源码根目录，采用 src layout：包代码放在 `src/<包名>/` 下，而非项目根目录。
这样 `import linear_cli` 只命中安装后的包，打包配置错误在本地立即暴露。

## 内容

| 条目 | 说明 |
|------|------|
| `linear_cli/` | 项目唯一的顶层 Python 包 |
