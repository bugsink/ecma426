from .model import Mapping, MappingIndex
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


def decode_mappings(
        mappings: str, sources: list[str], names: list[str], generated_column_offset=0, generated_line_offset=0) -> list[Mapping]:

    # Decodes a SourceMap "mappings" string into Tokens. Each token maps a (generated_line, generated_column) to a source location and
    # optional name. The string is structured as lines (separated by ';'), then segments (i.e. tokens) per line (','),
    # and finally fields within each segment (no delimiters needed, VLQs are self-delimiting). Segments have 1 field
    # (unmapped), 4 fields (mapped), or 5 fields (mapped with name).

    tokens = []
    if not mappings:
        return tokens

    source_idx = 0
    original_line = 0
    original_column = 0
    name_idx = 0
    name = None

    for generated_line, line in enumerate(mappings.split(";")):
        generated_column = generated_column_offset if generated_line == 0 else 0  # resets per generated line (first line may have offset)
        if line == "":
            continue  # empty line is fine

        for segment in line.split(","):
            # no empty segments per spec; they would be invalid input
            fields = decode_string(segment)
            if len(fields) not in (1, 4, 5):
                raise ValueError(f"invalid segment shape {len(fields)}: {segment!r}")

            generated_column_delta = fields[0]
            generated_column += generated_column_delta

            if len(fields) == 1:
                # unmapped segment (rationale: generated code with no origin, e.g. wrappers, helpers, polyfills).
                tokens.append(Mapping(
                    generated_line=generated_line + generated_line_offset, generated_column=generated_column, source="", original_line=0, original_column=0, name=None))
                continue

            # implied len(fields) in (4, 5)

            source_idx += fields[1]  # src_idx_delta
            if not (0 <= source_idx < len(sources)):
                raise ValueError(f"source index {source_idx} out of range")
            source = sources[source_idx]
            if source is None:
                source = ""

            original_line += fields[2]  # original_line_delta
            original_column += fields[3]  # original_column_delta

            if len(fields) == 5:
                name_idx += fields[4]
                if not (0 <= name_idx < len(names)):
                    raise ValueError(f"name index {name_idx} out of range")
                name = names[name_idx]
            else:
                name = None

            tokens.append(Mapping(
                generated_line=generated_line + generated_line_offset, generated_column=generated_column, source=source, original_line=original_line, original_column=original_column,
                name=name))

    return tokens


def encode_mappings(tokens: list[Mapping]) -> tuple[str, list[str], list[str]]:
    if not tokens:
        return "", [], []

    tokens_by_line: dict[int, list[Mapping]] = {}
    for t in sorted(tokens, key=lambda x: (x.generated_line, x.generated_column)):
        tokens_by_line.setdefault(t.generated_line, []).append(t)

    sources = IndexArray()
    names = IndexArray()

    source_idx = 0
    original_line = 0
    original_column = 0
    name_idx = 0

    per_dst_line = []

    for line_no in range(max(tokens_by_line) + 1 if tokens_by_line else 0):
        line_tokens = tokens_by_line.get(line_no, [])
        generated_column = 0  # resets per dst line
        segments = []

        for token in line_tokens:
            # start with 1 field
            fields = [token.generated_column - generated_column]  # generated_column delta
            generated_column = token.generated_column

            if token.source:
                # extend to 4 field version
                new_src_idx = sources.index_for(token.source)
                fields += [
                    new_src_idx - source_idx,
                    token.original_line - original_line,
                    token.original_column - original_column,
                ]
                source_idx, original_line, original_column = new_src_idx, token.original_line, token.original_column

                if token.name is not None:
                    # extend to 5 field version
                    new_name_idx = names.index_for(token.name)
                    fields += [new_name_idx - name_idx]
                    name_idx = new_name_idx

            segments.append(encode_values(fields))

        per_dst_line.append(",".join(segments))

    return ";".join(per_dst_line), sources.items, names.items


def _parse_source_map_fields(obj: dict) -> tuple[list[str | None], list[str], str]:
    sources_array = obj.get("sources", [])
    names_array = obj.get("names", [])
    mappings_string = obj.get("mappings", "")

    # ECMA-262 2024, §5 "Source map format" (bullet for sources):
    # Each entry is either a string that is a (potentially relative) URL or null if the source name is not known.
    if not isinstance(sources_array, list) or any(x is not None and not isinstance(x, str) for x in sources_array):
        raise TypeError("'sources' must be a list of strings")

    if not isinstance(sources_array, list) or any(x is not None and not isinstance(x, str) for x in sources_array):
        raise TypeError("'sources' must be a list of strings or nulls")
    if not isinstance(names_array, list) or any(not isinstance(x, str) for x in names_array):
        raise TypeError("'names' must be a list of strings")
    if not isinstance(mappings_string, str):
        raise TypeError("'mappings' must be a string")

    return sources_array, names_array, mappings_string


def decode_index_map(obj: dict) -> list[Mapping]:
    # sections is the key in the json object, the spec calls this an "index map"
    sections = obj.get("sections")
    if not isinstance(sections, list):
        raise TypeError("'sections' must be a list")

    tokens: list[Mapping] = []
    last_start: tuple[int, int] = (-1, -1)

    for section in sections:
        if not isinstance(section, dict):
            raise TypeError("each section must be an object")

        offset = section.get("offset")
        if not (isinstance(offset, dict) and
                isinstance(offset.get("line"), int) and
                isinstance(offset.get("column"), int)):
            raise TypeError("section.offset must be an object with integer 'line' and 'column'")

        start = (offset["line"], offset["column"])
        if start <= last_start:
            # spec: “The sections shall be sorted by starting position and shall not overlap.”
            raise ValueError("sections must be sorted by starting position and non-overlapping")

        embedded = section.get("map")
        if not isinstance(embedded, dict):
            raise TypeError("section.map must be an object")

        sources_array, names_array, mappings_string = _parse_source_map_fields(embedded)

        tokens.extend(
            decode_mappings(
                mappings_string,
                sources_array,
                names_array,
                generated_column_offset=offset["column"],
                generated_line_offset=offset["line"],
            )
        )
        last_start = start

    return tokens


def decode(obj: dict) -> MappingIndex:
    version = obj.get("version")
    if version is not None and version != 3:
        raise ValueError(f"unsupported version {version!r}; expected 3")

    if "sections" in obj:
        tokens = decode_index_map(obj)
        sources_for_index = []  # index maps don’t have a top-level sources array
    else:
        sources_array, names_array, mappings_string = _parse_source_map_fields(obj)
        tokens = decode_mappings(mappings_string, sources_array, names_array)
        sources_for_index = sources_array

    line_index = []
    index = {}
    for token in tokens:
        while len(line_index) <= token.generated_line:
            line_index.append([])
        line_index[token.generated_line].append(token.generated_column)
        index[(token.generated_line, token.generated_column)] = token

    return MappingIndex(obj, tokens, line_index, index, sources=sources_for_index)


def encode(tokens: list[Mapping], *, source_root: str | None = None, debug_id: str | None = None) -> dict:
    mappings_string, sources_array, names_array = encode_mappings(tokens)
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
