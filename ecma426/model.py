"""Interface-compatible with mattrobenolt/python-sourcemap (fresh impl)."""

from dataclasses import dataclass
from bisect import bisect_right
from typing import Dict, List, Optional, Tuple


@dataclass(eq=True)
class Token:
    """
    dst_line, dst_col: generated coordinates (0-based)
    src:               source filename or '' (unmapped)
    src_line, src_col: original coordinates (0-based)
    name:              optional symbol name or None
    """
    dst_line: int = 0
    dst_col: int = 0
    src: str = ""
    src_line: int = 0
    src_col: int = 0
    name: Optional[str] = None

    def __repr__(self) -> str:
        args = (self.src, self.dst_line, self.dst_col, self.src_line, self.src_col, self.name)
        return "<Token: src=%r dst_line=%d dst_col=%d src_line=%d src_col=%d name=%r>" % args


class SourceMapIndex:
    def __init__(self, raw, tokens: List[Token], line_index: List[List[int]],
                 index: Dict[Tuple[int, int], Token], sources: Optional[List[str]] = None):
        self.raw = raw
        self.tokens = tokens
        self.line_index = line_index
        self.index = index
        self.sources = sources or []

    def lookup(self, line: int, column: int) -> Token:
        """
        Lookup semantics: exact hit if present; otherwise use the nearest-left mapping on the same generated line (max
        dst_col <= column).
        Note: this is conventional (devtools, python-sourcemap), not mandated by ECMA-426.
        """

        try:
            return self.index[(line, column)]
        except KeyError:
            cols = self.line_index[line]
            i = bisect_right(cols, column)
            if not i:
                raise IndexError
            return self.index[(line, cols[i - 1])]

    def __getitem__(self, i):
        return self.tokens[i]

    def __iter__(self):
        return iter(self.tokens)

    def __len__(self):
        return len(self.tokens)

    def __repr__(self):
        return "<SourceMapIndex: %s>" % ", ".join(map(str, self.sources))
