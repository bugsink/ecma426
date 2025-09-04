# ecma426

A maintained, close-to-spec implementation of **ECMA-426: Source Maps** in pure Python.
Supports both decoding and encoding, including index maps with sections.

## Features

* **Up to date** — tracks the current [ECMA-426 spec](https://tc39.es/ecma426/).
* **Close to spec** — code is organized around spec sections, making it easy to verify correctness.
* **Pure Python** — no C extensions, no dependencies.
* **Both directions** — decode JSON maps into Python structures, encode tokens back to valid sourcemaps.
* **Sections supported** — index maps (`sections`) are handled according to the specification.

## Installation

```:::bash
pip install ecma426
```

## Usage

Top-level decode:

```:::python
import json
import ecma426

with open("app.min.js.map") as f:
    data = json.load(f)

smap = ecma426.loads(data)
print(smap.tokens[0])
```

Low-level encode / decode:

```:::python
from ecma426 import codec
from ecma426.model import Token

tokens = [
    Token(dst_line=0, dst_col=0, src="app.js", src_line=0, src_col=0, name=None)
]

# Encode into a sourcemap dict
smap = codec.encode(tokens)

# Decode back into a SourceMapIndex
decoded = codec.decode(smap)
```

## Future work / Roadmap

We are closely watching the spec for any [proposed changes](https://github.com/tc39/ecma426/tree/main/proposals).

Support for DebugIds (pass-through) is already included.


## Alternatives

* [python-sourcemap](https://github.com/mattrobenolt/python-sourcemap) -- only supports decoding, no sections.
* [evmar's python-sourcemap](https://github.com/evmar/python-sourcemap) -- unmaintained (13 years old).
* [Sentry's symbolic](https://github.com/getsentry/symbolic) -- much more than sourcemaps; Rust dependency.

## License

3-clause BSD, see [LICENSE](LICENSE).
