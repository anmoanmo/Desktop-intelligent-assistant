# 协作说明

本文档面向参与课程项目的小组成员，说明如何获取代码、配置本机环境、分工修改、提交代码和避免误提交本机文件。

## 仓库地址

远程仓库：

```bash
git@github.com:anmoanmo/Desktop-intelligent-assistant.git
```

首次拉取：

```bash
git clone git@github.com:anmoanmo/Desktop-intelligent-assistant.git
cd Desktop-intelligent-assistant
```

如果仓库已经存在本地，进入仓库后先同步远程：

```bash
git pull --rebase origin main
```

## 本地准备流程

每个组员第一次运行项目时建议按以下顺序操作：

1. 拉取最新代码。
2. 按 `docs/run-guide.md` 创建项目专用环境，或使用本机已有 Python 3.11 环境。
3. 复制 `.env.example` 为 `.env`。
4. 填写自己的 `DEEPSEEK_API_KEY`。
5. 确认 `DESKTOP_ASSISTANT_MODEL_DIRS=./Ark-Models-main`。
6. 执行配置检查。
7. 执行测试。

推荐命令：

```bash
bash scripts/setup.sh
conda activate desktop-assistant
cp .env.example .env
python -m desktop_assistant --check
python -m pytest
```

Windows 可使用：

```bat
scripts\setup.bat
conda activate desktop-assistant
copy .env.example .env
python -m desktop_assistant --check
python -m pytest
```

如果不创建新环境，先确认当前环境是 Python 3.11，再执行：

```bash
python -m pip install -e .
python -m desktop_assistant --check
python -m pytest
```

## 分支建议

- `main`：保持可运行版本，用于最终提交和演示。
- `docs/*`：文档修改分支，例如 `docs/report-material`。
- `feature/*`：功能开发分支，例如 `feature/profile-ui`。
- `fix/*`：缺陷修复分支，例如 `fix/model-scan-empty`。

简单文档修改可以直接在 `main` 上提交，但多人同时修改时建议每个人开分支，合并前先同步 `main`。

创建分支：

```bash
git checkout -b docs/report-material
```

同步主分支：

```bash
git checkout main
git pull --rebase origin main
```

把主分支更新合入自己的分支：

```bash
git checkout docs/report-material
git rebase main
```

## 分工建议

可以按模块分工，避免多人同时改同一批文件。

| 分工方向 | 主要文件 | 适合任务 |
| --- | --- | --- |
| 项目报告材料 | `technical-document.md`、`docs/*.md` | 整理报告、补充展示用例、记录测试 |
| 前端界面 | `src/desktop_assistant/ui/`、`qt_app.py` | 调整聊天窗口、设置面板、确认弹窗、角色展示 |
| 智能体与大模型 | `llm.py`、`service.py` | 调整 prompt、工具调用循环、主动提醒、记忆提取 |
| 工具与权限 | `tools.py`、`confirmations.py`、`audit.py` | 增加工具、修改权限策略、审计记录 |
| 模型资源扫描 | `models.py`、`model_sources.py`、`model_registry.py` | 模型目录解析、Live2D/Spine 扫描 |
| 配置与运行 | `settings.py`、`config/`、`scripts/` | 环境配置、启动脚本、检查命令 |
| 测试维护 | `tests/` | 增加或修复自动化测试 |

修改公共模块时，应提前在群里说明，避免多人同时改同一个文件产生冲突。

## 提交规范

提交信息使用中文，说明真实修改内容。建议使用“类型：内容”的格式。

常用类型：

- `初始化`：项目初始整理。
- `功能`：新增功能。
- `修复`：修复缺陷。
- `文档`：修改文档。
- `测试`：新增或调整测试。
- `配置`：修改环境、脚本或配置。
- `资源`：调整角色资源或资源说明。

示例：

```text
文档：补充报告技术材料
配置：增加本机 Python 环境运行说明
修复：处理模型目录为空时的提示
测试：补充工具权限检查用例
```

不要伪造提交历史，不要编造组员贡献，不要把多个无关修改塞进一个提交。

提交前建议查看变更：

```bash
git status --short
git diff
```

提交：

```bash
git add 需要提交的文件
git commit -m "文档：补充运行说明"
```

推送：

```bash
git push origin 当前分支名
```

## 提交前检查清单

每次提交前至少检查：

```bash
git status --short
python -m desktop_assistant --check
python -m pytest
```

如果使用项目专用 conda 环境，也可以执行：

```bash
conda run -n desktop-assistant python -m desktop_assistant --check
conda run -n desktop-assistant python -m pytest
```

只修改 Markdown 文档时，可以不跑完整 GUI，但建议至少检查链接、命令和文件名是否正确。

## 禁止提交内容

以下内容不得提交：

- `.env`、接口密钥、令牌、密码等敏感信息。
- `data/` 下的本地人设、记忆和聊天记录。
- `logs/` 下的工具调用日志。
- `node_modules/`。
- `.pytest_cache/`、`__pycache__/`、`*.pyc`。
- `dist/`、`build/`、`*.egg-info/`。
- 本机 IDE 配置和临时文件。
- 本机专用的 `config/settings.toml`。

如果不确定某个文件是否应该提交，先执行：

```bash
git status --short --ignored
```

被 `!!` 标记的文件是已忽略文件，通常不需要提交。

## 冲突处理

多人协作时，常见冲突来自 README、技术文档、配置模板和前端脚本。处理原则：

1. 先保存当前修改。
2. 执行 `git pull --rebase origin main`。
3. 如果出现冲突，打开冲突文件，保留双方有效内容。
4. 处理完成后执行 `git add 冲突文件`。
5. 继续 rebase：`git rebase --continue`。
6. 重新运行必要检查。

不要用强制覆盖方式解决冲突，除非已经和对应组员确认。

## 大文件与角色资源说明

`Ark-Models-main/` 角色资源纳入本仓库，用于课程学习和本地演示。资源体积较大，首次拉取、提交和推送需要预留时间。

注意事项：

- 不随意删除或重命名 `Ark-Models-main/` 中已有资源。
- 不把额外大型资源放入仓库，除非小组确认确实需要。
- `.png` 和 `.skel` 已通过 `.gitattributes` 标记为 binary，避免按文本方式处理差异。
- 《明日方舟》相关角色模型资源版权归上海鹰角网络有限公司所有，仅用于课程学习、技术研究和本地演示，不用于任何商业活动。

## 报告协作建议

最终报告建议由一名组员统一排版，其他组员提供各自负责模块的材料。可以按以下方式协作：

- 代码负责成员维护功能说明、运行截图和测试记录。
- 前端负责成员提供界面设计、窗口交互和角色渲染说明。
- 智能体负责成员提供 prompt、工具调用、记忆和权限设计说明。
- 文档负责成员将 `technical-document.md` 中的内容整理到 Word 模板。
- 所有成员各自补充个人总结和实际贡献。

`technical-document.md` 是报告整合材料，不等同于最终提交 PDF。最终报告仍需要按学校模板补充封面、成员信息、截图、表格、个人总结和排版。
