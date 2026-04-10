from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathValidator:
    base_dir: Path

    def validate(self, path: str | Path) -> Path:
        """
        Resolve the given path and ensure it's within base_dir.
        """
        p = Path(path)
        if not p.is_absolute():
            p = self.base_dir / p
        resolved = p.resolve()
        base = self.base_dir.resolve()
        try:
            resolved.relative_to(base)
        except Exception as e:
            raise ValueError("Path escapes sandbox") from e
        return resolved

