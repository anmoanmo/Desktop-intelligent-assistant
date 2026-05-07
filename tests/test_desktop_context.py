from desktop_assistant import desktop_context
from desktop_assistant.desktop_context import DesktopContextCollector


def test_windows_context_degrades_without_optional_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(desktop_context.sys, "platform", "win32")

    context = DesktopContextCollector().snapshot(include_ocr=True)

    assert context.platform == "Windows"
    assert context.permissions["accessibility"] == "unsupported"
    assert context.permissions["screen_recording"] == "unsupported"
    assert any("Windows" in note for note in context.permission_notes)
