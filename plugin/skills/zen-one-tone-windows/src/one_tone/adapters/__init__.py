from .antigravity import AntigravityAdapter
from .base import AdapterResult, AdapterStatus, ThemeAdapter, UnsupportedAdapter
from .chrome import ChromeAdapter
from .codex import CodexAdapter
from .matlab import MatlabAdapter
from .terminal import TerminalAdapter
from ..editor_instance import EditorSpec
from .vscode_family import VSCodeFamilyAdapter
from .windows import WindowsAdapter, WindowsConfig

__all__ = [
    "AdapterResult",
    "AdapterStatus",
    "AntigravityAdapter",
    "ChromeAdapter",
    "CodexAdapter",
    "EditorSpec",
    "MatlabAdapter",
    "TerminalAdapter",
    "ThemeAdapter",
    "UnsupportedAdapter",
    "VSCodeFamilyAdapter",
    "WindowsAdapter",
    "WindowsConfig",
]
