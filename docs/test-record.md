# 测试记录

## 测试环境

- 推荐 conda 环境：`desktop-assistant`
- 测试命令均在提交包根目录执行。

## 自动化测试

执行命令：

```bash
conda run -n desktop-assistant python -m pytest
```

提交包中执行结果：

```text
57 passed
```

测试全部通过，说明复制和文档整理没有影响现有代码行为。

## 配置检查

执行命令：

```bash
conda run -n desktop-assistant python -m desktop_assistant --check
```

检查内容：

- 配置能正常加载。
- 当前角色档案能初始化。
- 模型来源目录能被解析。
- `Ark-Models-main/` 中的 Spine 角色资源能被扫描。

提交包中执行结果显示：

```text
model_source_dirs: ["./Ark-Models-main"]
models_found: 886
model_kinds: ["spine38"]
```

## 提交前检查

```bash
git status --short
rg -n "开发辅助关键词" .
find Ark-Models-main -type f -size +100M -print
```

预期结果：

- Git 暂存内容不包含 `.env`、`data/`、`logs/`、`node_modules/` 和本机私有配置。
- 提交包文档不包含开发辅助痕迹。
- 角色资源不存在超过 100M 的单文件。
