from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import random
import sys
import threading

from .service import AssistantService
from .settings import AppSettings


def run_app(settings: AppSettings, extra_model_dirs: list[str] | None = None) -> int:
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", _default_chromium_flags())
    if os.environ.get("DESKTOP_ASSISTANT_ALLOW_UNSUPPORTED_GL_FLAGS") != "1":
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        sanitized = " ".join(part for part in flags.split() if part != "--use-gl=swiftshader")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = sanitized

    try:
        from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, QUrl, Signal, Slot
        from PySide6.QtGui import QColor
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication, QMainWindow
    except ImportError as exc:
        print(
            "缺少 PySide6/PySide6 WebEngine。请在 py311 中运行：\n"
            "  conda run -n py311 python -m pip install -e .\n"
            "或：\n"
            "  conda run -n py311 python -m pip install PySide6",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    class AssistantController:
        def __init__(self, service: AssistantService) -> None:
            self.service = service
            self.bridges: list[AssistantBridge] = []
            self.avatar_window: AssistantWindow | None = None
            self.main_window: AssistantWindow | None = None
            self.main_view = "chat"
            self._busy = False
            self._proactive_running = False
            self.proactive_timer = QTimer()
            self.proactive_timer.setSingleShot(True)
            self.proactive_timer.timeout.connect(self._on_proactive_timeout)

        def register_bridge(self, bridge: "AssistantBridge") -> None:
            self.bridges.append(bridge)

        def state_payload(self, window_kind: str | None = None) -> dict[str, Any]:
            payload = self.service.public_state()
            if window_kind == "main":
                payload["requested_view"] = self.main_view
            return payload

        def state_json(self, window_kind: str | None = None) -> str:
            return json.dumps(self.state_payload(window_kind), ensure_ascii=False)

        def broadcast_state(self) -> None:
            payload = self.state_json()
            for bridge in list(self.bridges):
                bridge.stateChanged.emit(payload)

        def broadcast(self, signal_name: str, *args: Any) -> None:
            for bridge in list(self.bridges):
                getattr(bridge, signal_name).emit(*args)

        def set_active_model(self, model_id: str) -> dict[str, Any]:
            result = self.service.set_active_model(model_id)
            self.broadcast_state()
            return {**result, "state": self.service.public_state()}

        def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
            result = self.service.save_settings(payload)
            if result.get("ok") and self.avatar_window is not None:
                self.avatar_window.apply_window_flags()
            self.configure_proactive_timer()
            self.broadcast_state()
            return result

        def create_profile(self, name: str) -> dict[str, Any]:
            result = self.service.create_profile(name)
            self._after_profile_change(result)
            return result

        def switch_profile(self, profile_id: str) -> dict[str, Any]:
            result = self.service.switch_profile(profile_id)
            self._after_profile_change(result)
            return result

        def rename_profile(self, profile_id: str, name: str) -> dict[str, Any]:
            result = self.service.rename_profile(profile_id, name)
            self.broadcast_state()
            return result

        def delete_profile(self, profile_id: str) -> dict[str, Any]:
            result = self.service.delete_profile(profile_id)
            self._after_profile_change(result)
            return result

        def _after_profile_change(self, result: dict[str, Any]) -> None:
            if result.get("ok"):
                for window in (self.avatar_window, self.main_window):
                    if window is None:
                        continue
                    window.apply_window_flags()
                    window.apply_saved_geometry()
                self.configure_proactive_timer()
            self.broadcast_state()

        def refresh_context(self) -> str:
            context = self.service.refresh_context()
            payload = json.dumps(context.to_dict(), ensure_ascii=False)
            self.broadcast("contextChanged", payload)
            self.broadcast_state()
            return payload

        def resolve_confirmation(self, request_id: str, approved: bool) -> dict[str, Any]:
            result = self.service.resolve_confirmation(request_id, approved)
            self.broadcast_state()
            return result

        def send_message(self, text: str) -> None:
            text = text.strip()
            if not text:
                return
            if self._busy:
                self.broadcast("error", "上一条消息还在处理中。")
                return
            self._busy = True
            self.broadcast("busyChanged", True)

            def run() -> None:
                full: list[str] = []
                try:
                    for delta in self.service.chat_stream(text):
                        full.append(delta)
                        self.broadcast("assistantDelta", delta)
                    self.broadcast("assistantDone", "".join(full))
                    self.broadcast_state()
                except Exception as exc:
                    self.broadcast("error", str(exc))
                finally:
                    self._busy = False
                    self.broadcast("busyChanged", False)

            threading.Thread(target=run, name="assistant-chat", daemon=True).start()

        def request_proactive(self) -> None:
            if self._busy or self._proactive_running:
                return
            self._proactive_running = True

            def run() -> None:
                try:
                    text = self.service.proactive_message()
                    if text:
                        self.broadcast("proactiveMessage", text)
                        self.broadcast_state()
                except Exception as exc:
                    self.broadcast("error", f"主动交流失败：{exc}")
                finally:
                    self._proactive_running = False

            threading.Thread(target=run, name="assistant-proactive", daemon=True).start()

        def open_main_window(self, view: str = "chat") -> None:
            self.main_view = view if view in {"chat", "settings"} else "chat"
            if self.main_window is None:
                return
            self._place_main_window_if_needed()
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
            self.broadcast("openView", self.main_view)

        def hide_main_window(self) -> None:
            if self.main_window is not None:
                self.main_window.hide()

        def configure_proactive_timer(self) -> None:
            self.proactive_timer.stop()
            if not self.service.settings.autonomy.enabled:
                return
            self.proactive_timer.start(self._next_proactive_interval_ms())

        def _on_proactive_timeout(self) -> None:
            self.request_proactive()
            self.configure_proactive_timer()

        def _next_proactive_interval_ms(self) -> int:
            autonomy = self.service.settings.autonomy
            minimum = max(30, int(autonomy.min_interval_seconds))
            maximum = max(minimum, int(autonomy.max_interval_seconds))
            return random.randint(minimum, maximum) * 1000

        def _place_main_window_if_needed(self) -> None:
            if self.main_window is None:
                return
            ui = self.service.settings.ui
            if ui.main_x or ui.main_y:
                return
            screen = self.main_window.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            geometry = screen.availableGeometry()
            x = geometry.right() - self.main_window.width() - 80
            y = geometry.top() + 80
            self.main_window.move(max(geometry.left(), x), max(geometry.top(), y))

    class AssistantWebPage(QWebEnginePage):
        def __init__(self, window_kind: str, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self.window_kind = window_kind

        def javaScriptConsoleMessage(
            self,
            level: QWebEnginePage.JavaScriptConsoleMessageLevel,
            message: str,
            line_number: int,
            source_id: str,
        ) -> None:
            level_name = getattr(level, "name", str(level))
            print(
                f"[web:{self.window_kind}:{level_name}] {source_id}:{line_number} {message}",
                file=sys.stderr,
            )

    class AssistantBridge(QObject):
        assistantDelta = Signal(str)
        assistantDone = Signal(str)
        proactiveMessage = Signal(str)
        busyChanged = Signal(bool)
        stateChanged = Signal(str)
        contextChanged = Signal(str)
        openView = Signal(str)
        error = Signal(str)

        def __init__(self, controller: AssistantController, window: "AssistantWindow", window_kind: str) -> None:
            super().__init__()
            self.controller = controller
            self.window = window
            self.window_kind = window_kind
            self.controller.register_bridge(self)

        def _window_payload(self) -> str:
            return json.dumps(
                {
                    "window": self.window_kind,
                    "x": self.window.x(),
                    "y": self.window.y(),
                    "width": self.window.width(),
                    "height": self.window.height(),
                },
                ensure_ascii=False,
            )

        def _clamp_window_to_screen(self) -> None:
            screen = self.window.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            geometry = screen.availableGeometry()
            max_x = max(geometry.left(), geometry.right() - self.window.width() + 1)
            max_y = max(geometry.top(), geometry.bottom() - self.window.height() + 1)
            x = min(max(self.window.x(), geometry.left()), max_x)
            y = min(max(self.window.y(), geometry.top()), max_y)
            self.window.move(x, y)

        @Slot(result=str)
        def getInitialState(self) -> str:
            return self.controller.state_json(self.window_kind)

        @Slot(result=str)
        def getWindowKind(self) -> str:
            return self.window_kind

        @Slot(int, int, result=str)
        def moveWindowBy(self, dx: int, dy: int) -> str:
            self.window.move(self.window.x() + dx, self.window.y() + dy)
            return self._window_payload()

        @Slot(int, int, result=str)
        def setWindowPosition(self, x: int, y: int) -> str:
            self.window.move(x, y)
            self._clamp_window_to_screen()
            return self._window_payload()

        @Slot(int, int, result=str)
        def resizeWindow(self, width: int, height: int) -> str:
            if self.window_kind == "main":
                width = max(320, min(1200, int(width)))
                height = max(360, min(1000, int(height)))
            else:
                width = max(180, min(900, int(width)))
                height = max(220, min(1100, int(height)))
            self.window.resize(width, height)
            self._clamp_window_to_screen()
            return self._window_payload()

        @Slot(str, result=str)
        def openMainWindow(self, view: str = "chat") -> str:
            self.controller.open_main_window(view)
            return self.controller.state_json(self.window_kind)

        @Slot(result=str)
        def hideMainWindow(self) -> str:
            self.controller.hide_main_window()
            return self.controller.state_json(self.window_kind)

        @Slot(result=str)
        def refreshContext(self) -> str:
            return self.controller.refresh_context()

        @Slot(str, result=str)
        def setActiveModel(self, model_id: str) -> str:
            return json.dumps(self.controller.set_active_model(model_id), ensure_ascii=False)

        @Slot(str, result=str)
        def saveSettings(self, json_payload: str) -> str:
            try:
                payload = json.loads(json_payload or "{}")
            except json.JSONDecodeError as exc:
                result = {"ok": False, "error": f"设置 JSON 无效：{exc.msg}", "state": self.controller.service.public_state()}
            else:
                result = self.controller.save_settings(payload)
            return json.dumps(result, ensure_ascii=False)

        @Slot(str, result=str)
        def createProfile(self, name: str) -> str:
            return json.dumps(self.controller.create_profile(name), ensure_ascii=False)

        @Slot(str, result=str)
        def switchProfile(self, profile_id: str) -> str:
            return json.dumps(self.controller.switch_profile(profile_id), ensure_ascii=False)

        @Slot(str, str, result=str)
        def renameProfile(self, profile_id: str, name: str) -> str:
            return json.dumps(self.controller.rename_profile(profile_id, name), ensure_ascii=False)

        @Slot(str, result=str)
        def deleteProfile(self, profile_id: str) -> str:
            return json.dumps(self.controller.delete_profile(profile_id), ensure_ascii=False)

        @Slot(result=str)
        def getPendingConfirmations(self) -> str:
            return json.dumps(self.controller.service.public_state().get("confirmations", []), ensure_ascii=False)

        @Slot(str, bool, result=str)
        def resolveConfirmation(self, request_id: str, approved: bool) -> str:
            return json.dumps(self.controller.resolve_confirmation(request_id, approved), ensure_ascii=False)

        @Slot(str)
        def sendMessage(self, text: str) -> None:
            self.controller.send_message(text)

        @Slot()
        def requestProactive(self) -> None:
            self.controller.request_proactive()

    class AssistantWindow(QMainWindow):
        def __init__(self, controller: AssistantController, window_kind: str) -> None:
            super().__init__()
            self.window_kind = window_kind
            self._native_level_warning_shown = False
            self.setWindowTitle("桌面智能体助手" if window_kind == "main" else "桌面智能体角色")
            self.apply_window_flags(show_after=False)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self._apply_initial_geometry()

            self.view = QWebEngineView(self)
            self.web_page = AssistantWebPage(window_kind, self.view)
            self.view.setPage(self.web_page)
            self.view.setAttribute(Qt.WA_TranslucentBackground, True)
            self.web_page.setBackgroundColor(QColor(0, 0, 0, 0))
            web_settings = self.view.settings()
            web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
            for attribute_name in ("WebGLEnabled", "Accelerated2dCanvasEnabled"):
                attribute = getattr(QWebEngineSettings, attribute_name, None)
                if attribute is not None:
                    web_settings.setAttribute(attribute, True)
            self.setCentralWidget(self.view)

            self.channel = QWebChannel(self.web_page)
            self.bridge = AssistantBridge(controller, self, window_kind)
            self.channel.registerObject("assistantBridge", self.bridge)
            self.web_page.setWebChannel(self.channel)

            ui_path = Path(__file__).resolve().parent / "ui" / "index.html"
            url = QUrl.fromLocalFile(str(ui_path))
            url.setQuery(f"mode={window_kind}")
            self.view.load(url)

        def apply_window_flags(self, show_after: bool = True) -> None:
            was_visible = self.isVisible()
            geometry = self.geometry()
            flags = Qt.FramelessWindowHint | Qt.Tool
            if self.window_kind == "avatar" and settings.ui.avatar_always_on_top:
                flags |= Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.setGeometry(geometry)
            if show_after and was_visible:
                self.show()
            self._apply_native_window_level()
            if show_after and was_visible and self.window_kind == "avatar" and settings.ui.avatar_always_on_top:
                self.raise_()
            if self.window_kind == "avatar":
                QTimer.singleShot(0, self._apply_native_window_level)

        def _apply_native_window_level(self) -> None:
            if self.window_kind != "avatar" or sys.platform != "darwin":
                return
            try:
                from ctypes import c_void_p

                import objc
                from AppKit import (
                    NSNormalWindowLevel,
                    NSStatusWindowLevel,
                    NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorFullScreenAuxiliary,
                    NSWindowCollectionBehaviorStationary,
                )

                ns_window = self._native_ns_window(objc, c_void_p)
                if ns_window is None:
                    return
                level = NSStatusWindowLevel if settings.ui.avatar_always_on_top else NSNormalWindowLevel
                ns_window.setLevel_(level)
                if settings.ui.avatar_always_on_top:
                    behavior = (
                        NSWindowCollectionBehaviorCanJoinAllSpaces
                        | NSWindowCollectionBehaviorStationary
                        | NSWindowCollectionBehaviorFullScreenAuxiliary
                    )
                    ns_window.setCollectionBehavior_(behavior)
                    if hasattr(ns_window, "setHidesOnDeactivate_"):
                        ns_window.setHidesOnDeactivate_(False)
                    if hasattr(ns_window, "setCanHide_"):
                        ns_window.setCanHide_(False)
                    ns_window.orderFrontRegardless()
                else:
                    ns_window.setCollectionBehavior_(0)
                    if hasattr(ns_window, "setHidesOnDeactivate_"):
                        ns_window.setHidesOnDeactivate_(True)
                    if hasattr(ns_window, "setCanHide_"):
                        ns_window.setCanHide_(True)
            except Exception as exc:
                if not self._native_level_warning_shown:
                    self._native_level_warning_shown = True
                    print(f"[qt:avatar] native window level unavailable: {exc}", file=sys.stderr)

        def _native_ns_window(self, objc: Any, c_void_p: Any) -> Any | None:
            native = objc.objc_object(c_void_p=c_void_p(int(self.winId())))
            candidates = [native]
            try:
                candidates.append(native.window())
            except Exception:
                pass
            for candidate in candidates:
                if candidate is not None and hasattr(candidate, "setLevel_"):
                    return candidate
            return None

        def showEvent(self, event: Any) -> None:
            super().showEvent(event)
            self._apply_native_window_level()
            QTimer.singleShot(0, self._apply_native_window_level)

        def _apply_initial_geometry(self) -> None:
            ui = settings.ui
            if self.window_kind == "main":
                self.resize(ui.main_width, ui.main_height)
                if ui.main_x or ui.main_y:
                    self.move(ui.main_x, ui.main_y)
                return

            avatar_width = int(320 * ui.avatar_scale) + 48
            avatar_height = int(420 * ui.avatar_scale) + 36
            self.resize(max(240, avatar_width), max(300, avatar_height))
            if ui.avatar_x or ui.avatar_y:
                self.move(ui.avatar_x, ui.avatar_y)

        def apply_saved_geometry(self) -> None:
            self._apply_initial_geometry()

    share_gl = getattr(Qt, "AA_ShareOpenGLContexts", None)
    if share_gl is None:
        share_gl = getattr(Qt.ApplicationAttribute, "AA_ShareOpenGLContexts", None)
    if share_gl is not None:
        QCoreApplication.setAttribute(share_gl, True)

    if os.environ.get("DESKTOP_ASSISTANT_QT_SOFTWARE_GL") == "1":
        software_gl = getattr(Qt, "AA_UseSoftwareOpenGL", None)
        if software_gl is None:
            software_gl = getattr(Qt.ApplicationAttribute, "AA_UseSoftwareOpenGL", None)
        if software_gl is not None:
            QCoreApplication.setAttribute(software_gl, True)

    app = QApplication(sys.argv)
    app.setApplicationName("桌面智能体助手")
    service = AssistantService(settings, extra_model_dirs=extra_model_dirs)
    controller = AssistantController(service)
    avatar_window = AssistantWindow(controller, "avatar")
    main_window = AssistantWindow(controller, "main")
    controller.avatar_window = avatar_window
    controller.main_window = main_window
    controller.configure_proactive_timer()

    avatar_window.show()
    main_window.hide()
    return app.exec()


def _default_chromium_flags() -> str:
    common = "--ignore-gpu-blocklist --enable-webgl --enable-webgl2 --enable-unsafe-swiftshader"
    if sys.platform == "darwin":
        return f"{common} --use-gl=angle --use-angle=metal --disable-gpu-compositing"
    if sys.platform.startswith("win"):
        return f"{common} --use-gl=angle --use-angle=d3d11"
    return common
