from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass


WM_CHAR = 0x0102

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD


class WindowInputError(RuntimeError):
    pass


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    visible: bool
    process_id: int


def send_key_to_window(
    key: str,
    title: str | None = None,
    *,
    contains: bool = False,
    class_name: str | None = "ANGBAND",
    process_id: int | None = None,
) -> None:
    if len(key) != 1:
        raise WindowInputError(f"expected one character key, got {key!r}")

    hwnd = find_window(title=title, contains=contains, class_name=class_name, process_id=process_id)
    if hwnd is None:
        raise WindowInputError("target Hengband window was not found")

    if not user32.PostMessageW(hwnd, WM_CHAR, ord(key), 0):
        error = ctypes.get_last_error()
        raise WindowInputError(f"PostMessageW failed with Windows error {error}")


def find_window_by_title(title: str, *, contains: bool = False) -> int | None:
    return find_window(title=title, contains=contains)


def find_window(
    *,
    title: str | None = None,
    contains: bool = False,
    class_name: str | None = None,
    process_id: int | None = None,
) -> int | None:
    matches: list[WindowInfo] = []
    for window in list_windows():
        if title is not None:
            title_lower = title.lower()
            window_title_lower = window.title.lower()
            if contains:
                if title_lower not in window_title_lower:
                    continue
            elif title_lower != window_title_lower:
                continue

        if class_name is not None and window.class_name != class_name:
            continue

        if process_id is not None and window.process_id != process_id:
            continue

        matches.append(window)

    if not matches:
        return None

    # Hengband owns several ANGBAND-class top-level windows; only the main term
    # (whose title is not "Term-N") processes input, so prefer it over whichever
    # sub term happens to come first in Z-order.
    def score(window: WindowInfo) -> int:
        return 0 if window.title.startswith("Term") else 1

    return max(matches, key=score).hwnd


def list_windows() -> list[WindowInfo]:
    found: list[WindowInfo] = []

    @EnumWindowsProc
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        window_title = _get_window_title(hwnd)
        class_name = _get_class_name(hwnd)
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        found.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=window_title,
                class_name=class_name,
                visible=True,
                process_id=int(process_id.value),
            )
        )

        return True

    if not user32.EnumWindows(callback, 0):
        error = ctypes.get_last_error()
        if error != 0:
            raise WindowInputError(f"EnumWindows failed with Windows error {error}")

    return found


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _get_class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value
