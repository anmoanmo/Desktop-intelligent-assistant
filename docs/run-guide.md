# 运行说明

## 环境要求

- Python 3.11
- 推荐 conda 环境名：`desktop-assistant`
- 主要依赖：`PySide6`、`openai`、`pytest`
- macOS 如需更完整桌面上下文，需要给终端或应用授权辅助功能权限

## 安装依赖

### 方式一：创建项目专用 conda 环境

推荐组员使用独立环境，避免和本机已有 Python 项目互相影响。

```bash
conda env create -f environment.yml
conda activate desktop-assistant
pip install -e .
```

如果环境已经存在，可以更新依赖：

```bash
conda env update -n desktop-assistant -f environment.yml --prune
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

### 方式二：不创建新环境，直接使用本机 Python 3.11

如果本机已经有可用的 Python 3.11 环境，也可以不创建新的 conda 环境，直接在当前环境中安装项目。使用这种方式前需要确认当前环境不会和其他项目依赖冲突。

先检查 Python 版本：

```bash
python --version
```

版本应为 `Python 3.11.x`。如果系统中同时存在多个 Python，可以使用：

```bash
python3.11 --version
```

确认版本后安装项目依赖：

```bash
pip install -e .
```

如果当前环境中 `pip` 对应的不是 Python 3.11，建议使用：

```bash
python -m pip install -e .
```

或：

```bash
python3.11 -m pip install -e .
```

安装后检查命令是否可用：

```bash
desktop-assistant --check
```

如果 `desktop-assistant` 不在 PATH 中，可以直接用模块方式运行：

```bash
python -m desktop_assistant --check
```

这种方式适合已经配置好 Python 3.11、PySide6 和相关依赖的组员。若出现依赖冲突、Qt 启动异常或系统包版本混乱，建议改用方式一创建项目专用环境。

## 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
DEEPSEEK_API_KEY=你的接口密钥
DESKTOP_ASSISTANT_MODEL_DIRS=./Ark-Models-main
```

多个模型目录在 macOS 和 Linux 下使用冒号分隔，在 Windows 下使用分号分隔。

## 启动应用

### 使用项目专用 conda 环境

macOS 或 Linux：

```bash
bash scripts/start.sh
```

Windows：

```bat
scripts\start.bat
```

直接启动：

```bash
desktop-assistant
```

备用启动方式：

```bash
conda run -n desktop-assistant python -m desktop_assistant
```

### 使用本机已有 Python 3.11 环境

如果采用“不创建新环境”的方式，先进入项目根目录，并确认已执行过 `pip install -e .`。然后运行：

```bash
desktop-assistant
```

如果命令不可用，使用模块方式：

```bash
python -m desktop_assistant
```

Windows 下同样可以使用：

```bat
python -m desktop_assistant
```

## 检查配置

项目专用 conda 环境：

```bash
conda run -n desktop-assistant python -m desktop_assistant --check
```

本机已有 Python 3.11 环境：

```bash
python -m desktop_assistant --check
```

检查命令不会启动图形界面，只会加载配置、创建服务对象并扫描模型目录。

## 运行测试

项目专用 conda 环境：

```bash
conda run -n desktop-assistant python -m pytest
```

本机已有 Python 3.11 环境：

```bash
python -m pytest
```

如果提示没有安装 `pytest`，执行：

```bash
python -m pip install pytest
```

## 常见问题

- 未配置接口密钥：确认 `.env` 中存在 `DEEPSEEK_API_KEY`，并且没有提交到仓库。
- 没有显示角色模型：确认 `DESKTOP_ASSISTANT_MODEL_DIRS` 指向 `Ark-Models-main` 或其他有效模型目录。
- `desktop-assistant` 命令不存在：先确认已经执行 `pip install -e .`，或者改用 `python -m desktop_assistant`。
- Python 版本不对：执行 `python --version` 检查版本，项目要求 Python 3.11。
- 依赖安装失败：优先使用项目专用 conda 环境；如果本机网络受限，可以让已安装成功的组员协助确认依赖来源。
- 桌面上下文不完整：macOS 下检查辅助功能权限；Windows 下部分上下文能力会降级。
- 前端角色渲染异常：确认 `src/desktop_assistant/ui/vendor/` 中存在 PixiJS、Live2D 和 Spine 运行库文件。
