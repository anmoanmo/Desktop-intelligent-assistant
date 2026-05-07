from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Callable
import json
import re

from openai import OpenAI

from .settings import LLMSettings
from .tools import TOOL_SPECS

WEB_TOOL_NAMES = {"open_url", "web_search"}
_WEB_ACTION_PATTERN = re.compile(
    r"(打开网页|网页搜索|搜索网页|上网查|联网查|网上查|用浏览器|打开链接|打开网址|访问链接|访问网址|"
    r"浏览器.{0,8}搜索|搜索一下|搜一下|为我搜索|帮我搜索|替我搜索|百度一下|谷歌一下|必应搜索|"
    r"Google\s*一下|Bing\s*搜索)",
    re.IGNORECASE,
)
_SEARCH_ACTION_PATTERN = re.compile(r"(搜索|搜一下|查一下|查询)")
_LOCAL_SEARCH_PATTERN = re.compile(r"(文件|文件夹|目录|本地|当前项目|代码|仓库|记忆|聊天记录|历史记录|设置)")
_EXPLICIT_WEB_CONTEXT_PATTERN = re.compile(r"(网页|浏览器|上网|联网|链接|网址|百度|谷歌|必应|Google|Bing)", re.IGNORECASE)
_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
_OPEN_URL_PATTERN = re.compile(r"(打开|访问|进入|浏览).{0,16}(https?://|www\.|链接|网址|URL)", re.IGNORECASE)
_MULTI_WEB_PATTERN = re.compile(r"(多个|几个|这些|以下|分别|全部|都打开|都搜索|逐个|批量|2\s*个|3\s*个|两[个个]?|三[个个]?)")


SYSTEM_PROMPT = """你是用户的跨平台智能桌面助理。
你可以根据桌面上下文帮助用户分析当前工作、回答问题，并在需要时调用工具打开文件、定位文件、打开网页或启动应用。
默认使用中文，表达简洁、可执行。
不要声称你看到了截图图片；除非工具返回 OCR 文本，否则你只知道结构化桌面文本上下文。
只有当用户明确要求“打开网页”、“搜索/搜一下”、“上网查”、“打开链接/网址”等网页动作时，才调用 web_search 或 open_url；普通聊天、知识问答、天气/新闻/价格等实时信息问题先用文字回答或询问是否需要网页搜索，不要自动跳转网页。
当用户明确网页搜索时，必须调用 web_search 并只传关键词；不要把网页搜索理解成本地文件搜索，也不要用 open_url 自行拼接搜索引擎 URL。web_search 失败或跳过通常是 Edge 启动、URL 打开或网页工具策略问题，不要误报为文件搜索权限不足。
对删除、移动、终端命令、发送消息、改系统设置等高风险操作，不要尝试执行，改为说明需要用户确认或手动处理。
当用户明确要求你记住某件事，或表达长期稳定偏好/身份/项目背景时，调用 save_memory 保存；不要保存敏感凭据。
"""

PROACTIVE_SYSTEM_PROMPT = """你是用户的跨平台智能桌面助理，可以在合适时主动和用户交流。
只在确实有帮助时发起一句简短提醒、建议或询问，例如发现用户停在错误、重复操作、长时间处于某个工作场景，或当前上下文与你的人设/记忆有关。
不要闲聊、不要刷存在感、不要频繁打断。若现在不值得打扰，只输出 SILENT。
"""

MEMORY_EXTRACTION_SYSTEM_PROMPT = """你负责从一轮对话中提炼值得长期本地保存的用户画像。
只提取稳定、可复用、非敏感的信息，例如学习目标、偏好、项目背景、工作流习惯、沟通偏好。
不要保存一次性任务、短期情绪、密钥、密码、验证码、令牌、身份证号、银行卡号或其他敏感内容。
只输出 JSON，不要输出解释。格式：
{"memories":[{"content":"...","category":"profile|preference|project|workflow|note","importance":0.0到1.0}]}
没有值得保存的信息时输出 {"memories":[]}。
"""


class LLMClient:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.resolve_api_key())

    def client(self) -> OpenAI:
        api_key = self.settings.resolve_api_key()
        if not api_key:
            raise RuntimeError(f"未配置 API key，请在根目录 .env 中设置 {self.settings.api_key_env}。")
        return OpenAI(
            api_key=api_key,
            base_url=self.settings.base_url,
            timeout=self.settings.timeout_seconds,
        )

    def chat_stream(
        self,
        user_text: str,
        desktop_prompt: str,
        persona_prompt: str,
        memory_prompt: str,
        history: list[dict[str, Any]],
        execute_tool: Callable[[str, str | dict[str, Any] | None], dict[str, Any]],
        max_tool_rounds: int = 4,
    ) -> Iterable[str]:
        if not self.configured:
            yield f"未配置 DeepSeek API key。请先在根目录 `.env` 中设置 `{self.settings.api_key_env}`。"
            return

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": persona_prompt},
            {"role": "system", "content": memory_prompt},
            {"role": "system", "content": desktop_prompt},
            *history,
            {"role": "user", "content": user_text},
        ]
        client = self.client()

        for _ in range(max_tool_rounds):
            response = client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                tools=tool_specs_for_user(user_text),
                tool_choice="auto",
                temperature=self.settings.temperature,
                stream=False,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                content = message.content or ""
                if content:
                    yield content
                return
            messages.append(message.model_dump(exclude_none=True))
            for tool_call in tool_calls:
                name = tool_call.function.name
                arguments = tool_call.function.arguments
                result = execute_tool(name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        messages.append(
            {
                "role": "system",
                "content": f"工具调用已达到 {max_tool_rounds} 轮上限。请基于已有工具结果给出最终答复，不要继续调用工具。",
            }
        )
        yield from self._stream_final(client, messages)

    def proactive_message(
        self,
        desktop_prompt: str,
        persona_prompt: str,
        memory_prompt: str,
        history: list[dict[str, Any]],
    ) -> str:
        if not self.configured:
            return ""

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": PROACTIVE_SYSTEM_PROMPT},
            {"role": "system", "content": persona_prompt},
            {"role": "system", "content": memory_prompt},
            {"role": "system", "content": desktop_prompt},
            *history[-6:],
            {
                "role": "user",
                "content": "根据当前桌面上下文判断是否需要主动对我说一句话。需要就直接说；不需要只输出 SILENT。",
            },
        ]
        response = self.client().chat.completions.create(
            model=self.settings.model,
            messages=messages,
            temperature=self.settings.temperature,
            stream=False,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content or content.upper() == "SILENT":
            return ""
        return content

    def extract_memories(
        self,
        user_text: str,
        assistant_text: str,
        persona_prompt: str,
        memory_prompt: str,
        max_entries: int = 3,
    ) -> list[dict[str, Any]]:
        if not self.configured or max_entries <= 0:
            return []

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT},
            {"role": "system", "content": persona_prompt},
            {"role": "system", "content": memory_prompt},
            {
                "role": "user",
                "content": (
                    "请从以下一轮对话中提炼长期记忆候选。\n\n"
                    f"用户：{user_text}\n\n"
                    f"助手：{assistant_text}\n\n"
                    f"最多返回 {max_entries} 条。"
                ),
            },
        ]
        response = self.client().chat.completions.create(
            model=self.settings.model,
            messages=messages,
            temperature=0,
            stream=False,
        )
        raw = (response.choices[0].message.content or "").strip()
        try:
            payload = json.loads(_json_payload(raw))
        except json.JSONDecodeError:
            return []
        memories = payload.get("memories")
        if not isinstance(memories, list):
            return []

        entries: list[dict[str, Any]] = []
        for item in memories[:max_entries]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            category = str(item.get("category") or "note").strip()
            if category not in {"profile", "preference", "project", "workflow", "note"}:
                category = "note"
            try:
                importance = float(item.get("importance", 0.5))
            except (TypeError, ValueError):
                importance = 0.5
            if content:
                entries.append({"content": content, "category": category, "importance": importance})
        return entries

    def _stream_final(self, client: OpenAI, messages: list[dict[str, Any]]) -> Iterable[str]:
        stream = client.chat.completions.create(
            model=self.settings.model,
            messages=messages,
            temperature=self.settings.temperature,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content


def _json_payload(value: str) -> str:
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return value


def allows_web_tools(user_text: str) -> bool:
    text = str(user_text or "").strip()
    if not text:
        return False
    if _LOCAL_SEARCH_PATTERN.search(text) and not _EXPLICIT_WEB_CONTEXT_PATTERN.search(text):
        return False
    if _WEB_ACTION_PATTERN.search(text):
        return True
    if _SEARCH_ACTION_PATTERN.search(text) and not _LOCAL_SEARCH_PATTERN.search(text):
        return True
    return _URL_PATTERN.search(text) is not None and _OPEN_URL_PATTERN.search(text) is not None


def allows_multiple_web_opens(user_text: str) -> bool:
    text = str(user_text or "")
    if not allows_web_tools(text):
        return False
    if len(_URL_PATTERN.findall(text)) > 1:
        return True
    return _MULTI_WEB_PATTERN.search(text) is not None


def tool_specs_for_user(user_text: str) -> list[dict[str, Any]]:
    if allows_web_tools(user_text):
        return TOOL_SPECS
    return [spec for spec in TOOL_SPECS if _tool_name(spec) not in WEB_TOOL_NAMES]


def _tool_name(spec: dict[str, Any]) -> str:
    function = spec.get("function")
    if not isinstance(function, dict):
        return ""
    return str(function.get("name") or "")
