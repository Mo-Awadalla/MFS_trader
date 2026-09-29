"""Import optional provider packages behind the extra that declares them.

Offline commands must work from a runtime-only install, so provider SDKs are
imported only by the code path that needs them. A missing provider raises
``MissingExtraError``; the CLIs turn it into an install hint and a nonzero exit.
"""

from __future__ import annotations

import importlib
from types import ModuleType

DISTRIBUTION = "mfs-trader"


class MissingExtraError(ImportError):
    """An optional dependency required by the requested operation is not installed."""

    def __init__(self, module: str, extra: str, purpose: str) -> None:
        self.module = module
        self.extra = extra
        self.purpose = purpose
        super().__init__(
            f"{purpose} requires the optional package '{module.split('.')[0]}', which is not "
            f"installed. Install it with: pip install '{DISTRIBUTION}[{extra}]'",
            name=module,
        )


def require_extra(module: str, *, extra: str, purpose: str) -> ModuleType:
    """Import ``module`` or raise ``MissingExtraError`` naming the extra to install."""

    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        # Do not misdiagnose a broken installed SDK as an absent extra.
        if exc.name and (module == exc.name or module.startswith(f"{exc.name}.")):
            raise MissingExtraError(module, extra, purpose) from exc
        raise
