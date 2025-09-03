#!/usr/bin/env python3
import sys
import json
from pathlib import Path

from ecma426.codec import encode
from ecma426.model import Token


def build_identity_line_tokens(js_text: str, js_path: str) -> list[Token]:
    """
    One mapped segment per generated line:
      (dst_line=i, dst_col=0) -> (src=js_path, src_line=i, src_col=0)
    """
    # Count lines like typical JS tooling: split on '\n'
    # Ensures a trailing newline still counts as a new (empty) line segment.
    line_count = js_text.count("\n") + 1
    return [
        Token(dst_line=i, dst_col=0, src=js_path, src_line=i, src_col=0, name=None)
        for i in range(line_count)
    ]


def main():
    if len(sys.argv) != 2:
        print("Usage: identity-sourcemap <file.js>")
        sys.exit(1)

    js_file = Path(sys.argv[1])
    if not js_file.exists():
        print(f"File not found: {js_file}")
        sys.exit(1)

    js_text = js_file.read_text(encoding="utf-8")
    tokens = build_identity_line_tokens(js_text, js_file.name)

    sourcemap = encode(tokens)

    sourcemap["file"] = js_file.name
    sourcemap["sourcesContent"] = [js_text]

    map_path = js_file.with_suffix(js_file.suffix + ".map")
    map_path.write_text(json.dumps(sourcemap, separators=(",", ":")), encoding="utf-8")

    print(f"Wrote {map_path}")


if __name__ == "__main__":
    main()
