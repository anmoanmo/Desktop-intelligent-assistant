# 桌面智能体助手

桌面智能体助手是一个面向学习、办公和日常桌面场景的智能桌面应用。项目以 Python 桌面程序为主体，结合大模型对话、桌面上下文读取、工具调用、长期记忆和 Live2D/Spine 角色渲染，实现一个可交互、可配置、可扩展的桌面智能体原型。

## 主要功能

- 桌面悬浮角色窗口：支持透明置顶、拖动、缩放和点击唤起聊天。
- 主聊天窗口：通过 OpenAI 兼容接口调用 DeepSeek 等大模型服务。
- 桌面上下文：读取前台应用、窗口标题和可用的结构化桌面信息，为回答提供上下文。
- 工具调用：支持打开网页、网页搜索、打开或定位本地路径、启动应用等低风险工具。
- 权限确认：高风险或需要谨慎处理的工具动作可以设置为每次询问。
- 长期记忆：保存稳定偏好、项目背景和工作流信息，并过滤明显敏感内容。
- 多角色档案：不同角色档案拥有独立的人设、记忆、窗口设置和聊天记录。
- 角色资源扫描：支持从本地目录发现 Spine 3.8 和 Live2D 模型资源。

## 目录结构

```text
src/desktop_assistant/      核心程序源码
src/desktop_assistant/ui/   桌面窗口前端页面和渲染逻辑
tests/                      自动化测试
config/                     配置模板
docs/                       中文技术文档
scripts/                    启动和资源脚本
Ark-Models-main/            课程演示用角色模型资源
```

## 环境准备

推荐为项目单独创建 conda 环境，默认环境名为 `desktop-assistant`。请在项目根目录执行：

```bash
conda env create -f environment.yml
conda activate desktop-assistant
pip install -e .
```

也可以使用脚本自动创建或更新环境：

```bash
bash scripts/setup.sh
conda activate desktop-assistant
```

Windows：

```bat
scripts\setup.bat
conda activate desktop-assistant
```

如果本机已经有可用的 Python 3.11 环境，也可以直接在该环境中安装：

```bash
pip install -e .
```

## 配置方法

复制环境变量模板：

```bash
cp .env.example .env
```

至少需要配置：

```bash
DEEPSEEK_API_KEY=你的接口密钥
DESKTOP_ASSISTANT_MODEL_DIRS=./Ark-Models-main
```

`.env` 只保存本机密钥和路径，不应提交到 Git。角色资源已经随提交包保存在 `Ark-Models-main/`，默认可以作为本地模型扫描目录。

## 启动方式

macOS 或 Linux：

```bash
bash scripts/start.sh
```

Windows：

```bat
scripts\start.bat
```

也可以直接运行：

```bash
desktop-assistant
```

如果命令不在 PATH 中：

```bash
conda run -n desktop-assistant python -m desktop_assistant
```

## 配置检查

不启动图形界面，只检查配置和模型扫描：

```bash
conda run -n desktop-assistant python -m desktop_assistant --check
```

检查结果会输出项目根目录、大模型配置、当前角色档案、模型来源目录、模型数量和模型类型。

## 测试

```bash
conda run -n desktop-assistant python -m pytest
```

当前提交包整理时，测试结果为 `57 passed`。

## 资源版权说明

本项目包含的《明日方舟》相关角色模型资源版权归上海鹰角网络有限公司所有。相关资源仅用于课程学习、技术研究和本地演示，不用于任何商业活动，不损害版权方利益。如需正式发布或商业使用，应另行取得权利方授权。

资源来源和格式说明见 `Ark-Models-main/README.md` 与 `docs/resource-notice.md`。

## 技术文档

- `technical-document.md`：面向课程报告整合的详细技术材料。
- `docs/technical-design.md`：项目模块和架构说明。
- `docs/run-guide.md`：运行环境和启动说明。
- `docs/collaboration-guide.md`：小组协作和提交规范。
- `docs/resource-notice.md`：角色资源来源和版权说明。
- `docs/test-record.md`：测试与检查记录。

## 协作要求

- 不提交 `.env`、运行日志、聊天记录、本机配置和密钥。
- Git 提交信息使用中文，描述真实修改内容。
- 修改大模型接口、工具调用或权限逻辑时，需要同步补充测试。
- 角色资源体积较大，首次克隆和推送需要预留足够时间。
