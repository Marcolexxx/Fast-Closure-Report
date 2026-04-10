from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class PathValidatorTest(unittest.TestCase):
    def test_blocks_escape(self) -> None:
        from app.security.path_validator import PathValidator

        base = Path("C:/tmp/aicopilot_sandbox")
        v = PathValidator(base_dir=base)
        with self.assertRaises(ValueError):
            v.validate("../secrets.txt")

    def test_allows_inside(self) -> None:
        from app.security.path_validator import PathValidator

        base = Path("C:/tmp/aicopilot_sandbox")
        v = PathValidator(base_dir=base)
        p = v.validate("proj/file.txt")
        self.assertTrue(str(p).lower().endswith("aicopilot_sandbox\\proj\\file.txt"))


if __name__ == "__main__":
    unittest.main()

