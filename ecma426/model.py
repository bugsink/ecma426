from dataclasses import dataclass
from bisect import bisect_right
from typing import Dict, List, Optional, Tuple


@dataclass(eq=True)
class Mapping:
    """
    generated_line, generated_column: generated coordinates (0-based)
    source:               source filename or '' (unmapped)
    original_line, original_column: original coordinates (0-based)
    name:              optional symbol name or None
    """
    generated_line: int = 0
    generated_column: int = 0
    source: str = ""
    original_line: int = 0
    original_column: int = 0
    name: Optional[str] = None

    def __repr__(self) -> str:
        args = (self.source, self.generated_line, self.generated_column, self.original_line, self.original_column, self.name)
        return "<Mapping: source=%r generated_line=%d generated_column=%d original_line=%d original_column=%d name=%r>" % args


class MappingIndex:
    def __init__(self, raw, tokens: List[Mapping], line_index: List[List[int]],
                 index: Dict[Tuple[int, int], Mapping], sources: Optional[List[str]] = None):
        self.raw = raw
        self.tokens = tokens
        self.line_index = line_index
        self.index = index
        self.sources = sources or []

    def lookup_left(self, line: int, column: int) -> Mapping:
        """
        Lookup semantics: exact hit if present; otherwise use the nearest-left mapping on the same generated line (max
        generated_column <= column).

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

    def __getitem__(self, key: Tuple[int, int]):
        return self.index[key]

    def __iter__(self):
        return iter(self.tokens)

    def __len__(self):
        return len(self.tokens)

    def __repr__(self):
        return "<MappingIndex: %s>" % ", ".join(map(str, self.sources))
