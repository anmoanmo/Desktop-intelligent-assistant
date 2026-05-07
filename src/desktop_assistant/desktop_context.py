from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import subprocess
import sys
import tempfile


@dataclass(slots=True)
class WindowInfo:
    owner: str | None = None
    title: str | None = None
    pid: int | None = None
    layer: int | None = None
    bounds: dict[str, Any] | None = None


@dataclass(slots=True)
class DesktopContext:
    platform: str
    frontmost_app: str | None = None
    frontmost_bundle_id: str | None = None
    frontmost_pid: int | None = None
    focused_window_title: str | None = None
    focused_element_text: str | None = None
    visible_windows: list[WindowInfo] = field(default_factory=list)
    ocr_text: str | None = None
    permission_notes: list[str] = field(default_factory=list)
    permissions: dict[str, str] = field(
        default_factory=lambda: {
            "accessibility": "unknown",
            "screen_recording": "not_requested",
            "ocr": "disabled",
        }
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    def to_prompt_text(self, max_chars: int = 5000) -> str:
        lines = [
            "当前桌面上下文：",
            f"- 平台：{self.platform}",
            f"- 前台应用：{self.frontmost_app or '未知'}",
            f"- Bundle ID：{self.frontmost_bundle_id or '未知'}",
            f"- 窗口标题：{self.focused_window_title or '未知'}",
        ]
        if self.focused_element_text:
            lines.append(f"- 焦点控件文本：{self.focused_element_text}")
        if self.visible_windows:
            lines.append("- 可见顶层窗口：")
            for window in self.visible_windows:
                owner = window.owner or "未知应用"
                title = window.title or "无标题"
                lines.append(f"  - {owner}: {title}")
        if self.ocr_text:
            lines.append("- 本地 OCR 文本：")
            lines.append(self.ocr_text)
        if self.permission_notes:
            lines.append("- 权限/采集说明：")
            lines.extend(f"  - {note}" for note in self.permission_notes)
        if self.permissions:
            lines.append("- 权限状态：")
            for name, status in self.permissions.items():
                lines.append(f"  - {name}: {status}")
        return "\n".join(lines)[:max_chars]


class DesktopContextCollector:
    def __init__(self, visible_window_limit: int = 8, ocr_languages: list[str] | None = None) -> None:
        self.visible_window_limit = visible_window_limit
        self.ocr_languages = ocr_languages or ["zh-Hans", "en-US"]

    def snapshot(self, include_ocr: bool = False, max_chars: int = 5000) -> DesktopContext:
        context = DesktopContext(platform=_platform_label())
        context.permissions["ocr"] = "requested" if include_ocr else "disabled"
        if sys.platform == "darwin":
            self._fill_frontmost_app(context)
            self._fill_accessibility_context(context)
            self._fill_visible_windows(context)
            if include_ocr:
                context.ocr_text = self._capture_screen_ocr(context)
        elif sys.platform.startswith("win"):
            context.permissions["accessibility"] = "unsupported"
            self._fill_windows_frontmost(context)
            self._fill_windows_visible_windows(context)
            if include_ocr:
                context.permissions["screen_recording"] = "unsupported"
                context.permission_notes.append("Windows OCR 截屏暂未实现；已跳过 OCR。")
        else:
            context.permissions["accessibility"] = "unsupported"
            context.permission_notes.append(f"{context.platform} 桌面上下文采集暂未实现。")
            if include_ocr:
                context.permissions["screen_recording"] = "unsupported"
                context.permission_notes.append(f"{context.platform} OCR 截屏暂未实现；已跳过 OCR。")
        if context.ocr_text and len(context.ocr_text) > max_chars:
            context.ocr_text = context.ocr_text[:max_chars]
        return context

    def _fill_frontmost_app(self, context: DesktopContext) -> None:
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return
            context.frontmost_app = str(app.localizedName() or "")
            context.frontmost_bundle_id = str(app.bundleIdentifier() or "")
            context.frontmost_pid = int(app.processIdentifier())
        except Exception as exc:  # pragma: no cover - depends on macOS runtime permissions
            context.permission_notes.append(f"无法读取前台应用：{exc}")

    def _fill_accessibility_context(self, context: DesktopContext) -> None:
        if not context.frontmost_pid:
            return
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
                AXUIElementCopyAttributeValue,
                AXUIElementCreateApplication,
                kAXFocusedUIElementAttribute,
                kAXFocusedWindowAttribute,
                kAXSelectedTextAttribute,
                kAXTitleAttribute,
                kAXTrustedCheckOptionPrompt,
                kAXValueAttribute,
            )

            trusted = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: False})
            if not trusted:
                context.permissions["accessibility"] = "denied"
                context.permission_notes.append("未授予 Accessibility 权限，焦点控件文本不可用。")
                return
            context.permissions["accessibility"] = "granted"

            app_ref = AXUIElementCreateApplication(context.frontmost_pid)
            focused_window = _ax_attr(AXUIElementCopyAttributeValue, app_ref, kAXFocusedWindowAttribute)
            if focused_window is not None:
                title = _ax_attr(AXUIElementCopyAttributeValue, focused_window, kAXTitleAttribute)
                if title:
                    context.focused_window_title = str(title)

            focused = _ax_attr(AXUIElementCopyAttributeValue, app_ref, kAXFocusedUIElementAttribute)
            if focused is not None:
                selected = _ax_attr(AXUIElementCopyAttributeValue, focused, kAXSelectedTextAttribute)
                value = selected or _ax_attr(AXUIElementCopyAttributeValue, focused, kAXValueAttribute)
                if value:
                    context.focused_element_text = str(value)[:2000]
        except Exception as exc:  # pragma: no cover - depends on macOS runtime permissions
            context.permissions["accessibility"] = "error"
            context.permission_notes.append(f"Accessibility 读取失败：{exc}")

    def _fill_visible_windows(self, context: DesktopContext) -> None:
        try:
            import Quartz

            options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
            windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
            for item in windows[: self.visible_window_limit * 3]:
                owner = item.get("kCGWindowOwnerName")
                title = item.get("kCGWindowName")
                layer = item.get("kCGWindowLayer")
                if layer not in (0, None):
                    continue
                if not owner and not title:
                    continue
                context.visible_windows.append(
                    WindowInfo(
                        owner=str(owner) if owner else None,
                        title=str(title) if title else None,
                        pid=int(item["kCGWindowOwnerPID"]) if item.get("kCGWindowOwnerPID") else None,
                        layer=int(layer) if layer is not None else None,
                        bounds=dict(item.get("kCGWindowBounds", {})),
                    )
                )
                if len(context.visible_windows) >= self.visible_window_limit:
                    break
        except Exception as exc:  # pragma: no cover - depends on macOS runtime permissions
            context.permission_notes.append(f"窗口列表读取失败：{exc}")

    def _capture_screen_ocr(self, context: DesktopContext) -> str | None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            screenshot_path = Path(handle.name)
        try:
            subprocess.run(
                ["screencapture", "-x", str(screenshot_path)],
                check=True,
                timeout=8,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            context.permissions["screen_recording"] = "granted"
            return _vision_ocr(screenshot_path, self.ocr_languages)
        except Exception as exc:  # pragma: no cover - depends on macOS permissions
            context.permissions["screen_recording"] = "denied_or_error"
            context.permission_notes.append(f"OCR 截屏读取失败：{exc}")
            return None
        finally:
            try:
                screenshot_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _fill_windows_frontmost(self, context: DesktopContext) -> None:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return
            context.focused_window_title = _windows_window_title(user32, hwnd)
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                context.frontmost_pid = int(pid.value)
            context.frontmost_app = context.focused_window_title or "Windows"
        except Exception as exc:  # pragma: no cover - depends on Windows runtime
            context.permission_notes.append(f"Windows 前台窗口读取失败：{exc}")

    def _fill_windows_visible_windows(self, context: DesktopContext) -> None:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def callback(hwnd: int, _lparam: int) -> bool:
                if len(context.visible_windows) >= self.visible_window_limit:
                    return False
                if not user32.IsWindowVisible(hwnd):
                    return True
                title = _windows_window_title(user32, hwnd)
                if not title:
                    return True
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                context.visible_windows.append(
                    WindowInfo(
                        title=title,
                        pid=int(pid.value) if pid.value else None,
                    )
                )
                return True

            user32.EnumWindows(enum_proc_type(callback), 0)
        except Exception as exc:  # pragma: no cover - depends on Windows runtime
            context.permission_notes.append(f"Windows 窗口列表读取失败：{exc}")


def _ax_attr(copy_func: Any, element: Any, attr: Any) -> Any:
    result = copy_func(element, attr, None)
    if isinstance(result, tuple):
        if len(result) == 2:
            err, value = result
            return value if err == 0 else None
        return result[-1]
    return result


def _platform_label() -> str:
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("win"):
        return "Windows"
    if sys.platform.startswith("linux"):
        return "Linux"
    return sys.platform


def _windows_window_title(user32: Any, hwnd: int) -> str | None:
    try:
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return None
        import ctypes

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return str(buffer.value).strip() or None
    except Exception:
        return None


def _vision_ocr(image_path: Path, languages: list[str]) -> str | None:
    try:
        import Foundation
        import Vision

        url = Foundation.NSURL.fileURLWithPath_(str(image_path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLanguages_(languages)
        request.setUsesLanguageCorrection_(True)
        if hasattr(Vision, "VNRequestTextRecognitionLevelAccurate"):
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        result = handler.performRequests_error_([request], None)
        if isinstance(result, tuple) and not result[0]:
            return None
        lines: list[str] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if candidates:
                lines.append(str(candidates[0].string()))
        return "\n".join(lines).strip() or None
    except Exception:
        return None
