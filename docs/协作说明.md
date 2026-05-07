# 协作说明

## 仓库地址

远程仓库：

```bash
git@github.com:anmoanmo/Desktop-intelligent-assistant.git
```

## 分支建议

- `main`：保持可运行版本。
- 功能开发可以从 `main` 新建分支，完成后合并。
- 修改大模型接口、工具调用、权限控制和记忆逻辑时，应同步运行测试。

## 提交规范

提交信息使用中文，说明真实修改内容。例如：

```text
初始化：整理桌面智能体助手提交包
修复：处理模型目录为空时的提示
文档：补充角色资源使用说明
```

不要伪造提交历史，不要编造组员贡献。

## 禁止提交内容

- `.env`、接口密钥、令牌、密码等敏感信息。
- `data/` 下的本地人设、记忆和聊天记录。
- `logs/` 下的工具调用日志。
- `node_modules/`、缓存目录、构建产物和本机 IDE 配置。
- 本机专用的 `config/settings.toml` 和 `config/model_sources.toml`。

## 大文件说明

`Ark-Models-main/` 角色资源纳入本仓库，用于课程学习和本地演示。资源体积较大，首次拉取、提交和推送需要预留时间。二进制资源通过 `.gitattributes` 标记为 binary，避免 Git 按文本方式处理差异。
