"""Press a button or an option of the CoWork application through the macOS Accessibility API.

An approval box is answered by pressing its own button, found by label: no mouse and no key, so
the layout, the keyboard focus and the frontmost application do not matter. A key reaches the
box only when the composer does not hold the keyboard, and the folder box never takes one.
A question is answered the same way, one step per call: its options are checkboxes. The digit
shortcut stopped working after the Cowork update of 10 Nov 2026, and a digit now types into the
card's "Something else" text field. Measured on macOS 26 with the interaction probe.
docs/cowork_desktop.md.

The application exposes its tree once AXManualAccessibility is set, which an Electron
application waits for. One walk of the tree takes well under a second.
"""

from __future__ import annotations

import ctypes
import re
import subprocess
from collections.abc import Iterator

_APPLICATION_SERVICES = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_UTF8 = 0x08000100
_SINT32 = 3
_DEPTH = 40

# A button carries its shortcut digit in its label: "Deny 1", "Allow once 2".
_SHORTCUT = re.compile(r"\s+\d$")

# The group that holds a question card is labelled "<question> Choose one of N options." or
# "... Choose one or more of N options."
_CARD = "Choose one"
# What moves a card on once an option is chosen, in the order tried. "Skip", "Minimize" and
# "Previous question" are never pressed.
_STEP_BUTTONS = ("Submit", "Send", "Done", "Next question")


class _Tree:
    """The accessibility tree of one running application, read and pressed. Not thread safe.

    `OSError` when the process is not running. Use it as a context manager: it releases every
    value it copied.
    """

    def __init__(self, process: str) -> None:
        found = subprocess.run(
            ["pgrep", "-x", process], capture_output=True, text=True, check=False
        )
        if not found.stdout.split():
            raise OSError(f"{process} is not running")
        self._ax, self._cf = ctypes.CDLL(_APPLICATION_SERVICES), ctypes.CDLL(_CORE_FOUNDATION)
        _declare(self._ax, self._cf)
        self._owned: list[int] = []
        self._names = {n: self._name(n) for n in _ATTRIBUTES}
        self.app = self._ax.AXUIElementCreateApplication(int(found.stdout.split()[0]))
        self._owned.append(self.app)
        true = ctypes.c_void_p.in_dll(self._cf, "kCFBooleanTrue")
        self._ax.AXUIElementSetAttributeValue(self.app, self._name("AXManualAccessibility"), true)

    def __enter__(self) -> _Tree:
        return self

    def __exit__(self, *_: object) -> None:
        for value in self._owned:
            self._cf.CFRelease(value)

    def _name(self, text: str) -> int:
        value = self._cf.CFStringCreateWithCString(None, text.encode(), _UTF8)
        self._owned.append(value)
        return value

    def _copy(self, element: int, attribute: str) -> int | None:
        value = ctypes.c_void_p()
        if (
            self._ax.AXUIElementCopyAttributeValue(
                element, self._names[attribute], ctypes.byref(value)
            )
            != 0
        ):
            return None
        self._owned.append(value.value)
        return value.value

    def text(self, element: int, attribute: str) -> str:
        value = self._copy(element, attribute)
        if not value or self._cf.CFGetTypeID(value) != self._cf.CFStringGetTypeID():
            return ""
        buffer = ctypes.create_string_buffer(1024)
        self._cf.CFStringGetCString(value, buffer, 1024, _UTF8)
        return buffer.value.decode(errors="replace")

    def number(self, element: int, attribute: str) -> int | None:
        """A number or a boolean attribute, such as a checkbox's AXValue. None when it has none."""
        value = self._copy(element, attribute)
        if not value:
            return None
        kind = self._cf.CFGetTypeID(value)
        if kind == self._cf.CFBooleanGetTypeID():
            return int(bool(self._cf.CFBooleanGetValue(value)))
        if kind == self._cf.CFNumberGetTypeID():
            out = ctypes.c_int()
            self._cf.CFNumberGetValue(value, _SINT32, ctypes.byref(out))
            return out.value
        return None

    def label(self, element: int) -> str:
        return (
            self.text(element, "AXTitle")
            or self.text(element, "AXDescription")
            or self.text(element, "AXValue")
        )

    def role(self, element: int) -> str:
        return self.text(element, "AXRole")

    def children(self, element: int) -> list[int]:
        kids = self._copy(element, "AXChildren")
        if not kids or self._cf.CFGetTypeID(kids) != self._cf.CFArrayGetTypeID():
            return []
        return [
            self._cf.CFArrayGetValueAtIndex(kids, i) for i in range(self._cf.CFArrayGetCount(kids))
        ]

    def walk(self, root: int) -> Iterator[tuple[int, int]]:
        """Every element under `root`, root included, in document order, with its depth."""
        stack = [(root, 0)]
        while stack:
            element, depth = stack.pop()
            yield element, depth
            if depth < _DEPTH:
                stack.extend((kid, depth + 1) for kid in reversed(self.children(element)))

    def press(self, element: int) -> bool:
        return self._ax.AXUIElementPerformAction(element, self._name("AXPress")) == 0


def press_button(process: str, labels: tuple[str, ...]) -> bool:
    """Press the first button of `process` labelled one of `labels`. False when there is none.

    A label matches with its trailing shortcut digit dropped. `OSError` when the process is
    not running.
    """
    with _Tree(process) as tree:
        for element, _ in tree.walk(tree.app):
            is_button = tree.role(element) == "AXButton"
            if is_button and _SHORTCUT.sub("", tree.label(element).strip()) in labels:
                return tree.press(element)
        return False


def answer_question(process: str) -> tuple[bool, str]:
    """One step of answering the question card on screen with its first option.

    A card shows one question at a time. If no option of it is chosen, this chooses the first.
    Otherwise it presses the button that moves the card on: Submit, or Next question. A
    question is answered by calling this until the card is gone. It returns whether it pressed
    something and a line describing the card as it found it, for the log. `OSError` when the
    process is not running.
    """
    with _Tree(process) as tree:
        card = next(
            (
                element
                for element, _ in tree.walk(tree.app)
                if tree.role(element) == "AXGroup" and _CARD in tree.label(element)
            ),
            None,
        )
        if card is None:
            return False, "no question card on screen"
        boxes: list[tuple[int, str, int | None]] = []
        buttons: list[tuple[int, str]] = []
        for element, _ in tree.walk(card):
            role = tree.role(element)
            if role == "AXCheckBox":
                boxes.append((element, tree.label(element), tree.number(element, "AXValue")))
            elif role == "AXButton":
                buttons.append((element, tree.label(element)))
        seen = (
            f"{tree.label(card)!r}; options "
            + ", ".join(f"{label!r}={value}" for _, label, value in boxes)
            + "; buttons "
            + ", ".join(repr(label) for _, label in buttons)
        )
        if boxes and not any(value for _, _, value in boxes):
            element, label, _ = boxes[0]
            return tree.press(element), f"chose {label!r}; {seen}"
        for want in _STEP_BUTTONS:
            for element, label in buttons:
                if label == want or label.startswith(want + " "):
                    return tree.press(element), f"pressed {label!r}; {seen}"
        return False, f"nothing to press; {seen}"


_ATTRIBUTES = (
    "AXRole",
    "AXTitle",
    "AXDescription",
    "AXValue",
    "AXChildren",
)


def _declare(ax: ctypes.CDLL, cf: ctypes.CDLL) -> None:
    pointer = ctypes.c_void_p
    cf.CFStringCreateWithCString.restype = pointer
    cf.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringGetCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFGetTypeID.argtypes = [pointer]
    cf.CFGetTypeID.restype = ctypes.c_ulong
    cf.CFStringGetTypeID.restype = ctypes.c_ulong
    cf.CFArrayGetTypeID.restype = ctypes.c_ulong
    cf.CFBooleanGetTypeID.restype = ctypes.c_ulong
    cf.CFNumberGetTypeID.restype = ctypes.c_ulong
    cf.CFBooleanGetValue.argtypes = [pointer]
    cf.CFBooleanGetValue.restype = ctypes.c_ubyte
    cf.CFNumberGetValue.argtypes = [pointer, ctypes.c_int, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_ubyte
    cf.CFArrayGetCount.argtypes = [pointer]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetValueAtIndex.argtypes = [pointer, ctypes.c_long]
    cf.CFArrayGetValueAtIndex.restype = pointer
    cf.CFRelease.argtypes = [pointer]
    ax.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
    ax.AXUIElementCreateApplication.restype = pointer
    ax.AXUIElementCopyAttributeValue.argtypes = [pointer, pointer, ctypes.POINTER(pointer)]
    ax.AXUIElementSetAttributeValue.argtypes = [pointer, pointer, pointer]
    ax.AXUIElementPerformAction.argtypes = [pointer, pointer]
