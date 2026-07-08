"""Tool package — each submodule self-registers via `@tool(...)`.

Importing this package imports every tool module, triggering decorator-based
registration into the shared registry in `_registry.py`. The server calls
`build_registry(enabled_features)` to get the active subset for the session.
"""

from __future__ import annotations

from ._registry import ToolSpec, all_tools, build_registry, tool

# Import side effects register each module's tools. Keep these imports even
# though they look unused — removing them unregisters the tools.
from . import calendar_tools  # noqa: F401
from . import docs_tools  # noqa: F401
from . import drive_tools  # noqa: F401
from . import gmail_bulk  # noqa: F401
from . import gmail_classify  # noqa: F401
from . import gmail_compose  # noqa: F401
from . import gmail_filters  # noqa: F401
from . import gmail_labels  # noqa: F401
from . import gmail_messages  # noqa: F401
from . import gmail_rules  # noqa: F401
from . import sheets_tools  # noqa: F401
from . import slides_tools  # noqa: F401
from . import tasks_tools  # noqa: F401

# Back-compat: old callers imported ALL_TOOLS as a module attribute.
ALL_TOOLS = all_tools()

__all__ = ["ToolSpec", "all_tools", "build_registry", "tool", "ALL_TOOLS"]
