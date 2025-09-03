import json

from .model import Token, SourceMapIndex
from .vlq import decode_string, encode_values


class IndexArray:
    """Array of unique strings with index lookup."""

    def __init__(self):
        self._index = {}
        self._items = []

    def index_for(self, value: str) -> int:
        idx = self._index.get(value)
        if idx is None:
            idx = len(self._items)
            self._index[value] = idx
            self._items.append(value)
        return idx

    @property
    def items(self) -> list[str]:
        return self._items


def decode_mappings(mappings: str, sources: list[str], names: list[str]) -> list[Token]:
    tokens = []
    if not mappings:
        return tokens

    src_idx = 0
    src_line = 0
    src_col = 0
    name_idx = 0
    name = None

    for dst_line, line in enumerate(mappings.split(";")):
        dst_col = 0  # resets per generated line
        if line == "":
            continue  # empty line is fine

        for segment in line.split(","):
            # no empty segments per spec; they would be invalid input
            fields = decode_string(segment)
            if len(fields) not in (1, 4, 5):
                raise ValueError(f"invalid segment shape {len(fields)}: {segment!r}")

            dst_col_delta = fields[0]
            dst_col += dst_col_delta

            if len(fields) == 1:
                # unmapped segment
                tokens.append(Token(dst_line=dst_line, dst_col=dst_col, src="", src_line=0, src_col=0, name=None))
                continue

            # implied len(fields) in (4, 5)

            src_idx += fields[1]  # src_idx_delta
            if not (0 <= src_idx < len(sources)):
                raise ValueError(f"source index {src_idx} out of range")
            src = sources[src_idx]

            src_line += fields[2]  # src_line_delta
            src_col += fields[3]  # src_col_delta

            if len(fields) == 5:
                name_idx += fields[4]
                if not (0 <= name_idx < len(names)):
                    raise ValueError(f"name index {name_idx} out of range")
                name = names[name_idx]
            else:
                name = None

            tokens.append(Token(
                dst_line=dst_line, dst_col=dst_col, src=src, src_line=src_line, src_col=src_col, name=name))

    return tokens


def encode_tokens(tokens: list[Token]) -> tuple[str, list[str], list[str]]:
    if not tokens:
        return "", [], []

    tokens_by_line: dict[int, list[Token]] = {}
    for t in sorted(tokens, key=lambda x: (x.dst_line, x.dst_col)):
        tokens_by_line.setdefault(t.dst_line, []).append(t)

    sources = IndexArray()
    names = IndexArray()

    src_idx = 0
    src_line = 0
    src_col = 0
    name_idx = 0

    per_dst_line = []

    for line_no in range(max(tokens_by_line) + 1 if tokens_by_line else 0):
        line_tokens = tokens_by_line.get(line_no, [])
        dst_col = 0  # resets per dst line
        segments = []

        for token in line_tokens:
            # start with 1 field
            fields = [token.dst_col - dst_col]  # dst_col delta
            dst_col = token.dst_col

            if token.src:
                # extend to 4 field version
                new_src_idx = sources.index_for(token.src)
                fields += [
                    new_src_idx - src_idx,
                    token.src_line - src_line,
                    token.src_col - src_col,
                ]
                src_idx, src_line, src_col = new_src_idx, token.src_line, token.src_col

                if token.name is not None:
                    # extend to 5 field version
                    new_name_idx = names.index_for(token.name)
                    fields += [new_name_idx - name_idx]
                    name_idx = new_name_idx

            segments.append(encode_values(fields))

        per_dst_line.append(",".join(segments))

    return ";".join(per_dst_line), sources.items, names.items


def _strip_xssi_prefix(s: str) -> str:
    if s.startswith(")]}'") or s.startswith(")]}"):
        return s.split("\n", 1)[1]
    return s


def decode(obj: str | dict) -> SourceMapIndex:
    if isinstance(obj, str):
        obj = json.loads(_strip_xssi_prefix(obj))
    if not isinstance(obj, dict):
        raise TypeError("sourcemap must be a JSON object or JSON string")

    version = obj.get("version")
    if version is not None and version != 3:
        raise ValueError(f"unsupported version {version!r}; expected 3")

    sources_array = obj.get("sources", [])
    names_array = obj.get("names", [])
    mappings_string = obj.get("mappings", "")

    if not isinstance(sources_array, list) or any(not isinstance(x, str) for x in sources_array):
        raise TypeError("'sources' must be a list of strings")
    if not isinstance(names_array, list) or any(not isinstance(x, str) for x in names_array):
        raise TypeError("'names' must be a list of strings")
    if not isinstance(mappings_string, str):
        raise TypeError("'mappings' must be a string")

    tokens = decode_mappings(mappings_string, sources_array, names_array)

    line_index = []
    index = {}
    for token in tokens:
        while len(line_index) <= token.dst_line:
            line_index.append([])
        line_index[token.dst_line].append(token.dst_col)
        index[(token.dst_line, token.dst_col)] = token

    return SourceMapIndex(obj, tokens, line_index, index, sources=sources_array)


def encode(tokens: list[Token], *, source_root: str | None = None, debug_id: str | None = None) -> dict:
    mappings_string, sources_array, names_array = encode_tokens(tokens)
    out = {
        "version": 3,
        "sources": sources_array,
        "names": names_array,
        "mappings": mappings_string,
    }

    if source_root is not None:
        out["sourceRoot"] = source_root

    if debug_id is not None:
        out["debugId"] = debug_id

    return out
