# ecma426

Python implementation of the ECMA-426 Source map format specification

This library targets the ECMA-426 Source Map format (1st edition) and tracks the living draft for changes. The core VLQ `mappings` format is stable; new features are additive. We will adopt them as they reach consensus.

**Actively watching:**

- **Living spec & repo.** The ECMA-426 living draft and TC39 repository for ongoing edits and issues.
  - Latest published snapshot: ECMA-426 (Dec 2024).
  - Living spec: tc39.es/source-map.

- **Debug IDs.** Self-identifying bundles + maps via a `debugId` field and a matching marker in the generated file. This repo already accepts/encodes `"debugId"` as an optional string.

- **Scopes.** Structured variable/function scope data alongside `mappings` to improve stepping and locals in debuggers. Reference codec exists; expected to ship as additional fields, not changes to `mappings`.

## Understanding the spec

The [spec](https://ecma-international.org/publications-and-standards/standards/ecma-426/) is precise but lacks exposure
of intention and high-level concepts. The below is my attempt to fill in the gaps.

### Intention of source maps

A source map lets you say:

> This piece of generated code (what the runtime executes) came from this place in my original sources.

* **Destination (dst)** = coordinates in the *generated* file (what the browser runs).
* **Source (src)** = coordinates in the *original* file (before minify/transpile).

So when an error happens at `bundle.js:1:853`, the map can tell you it’s really `foo.ts:42:7`.

### Key concepts

* **Token**: one mapping: `(dst_line, dst_col)` → `(src_file, src_line, src_col, optional name)`.

* **Mappings string**: a compact encoding of all tokens, structured as:

  * **Lines**: separated by semicolons (`;`), each line corresponds to a line in the generated file.
  * **Segments**: within each line, separated by commas (`,`), each segment encodes one token.
  * **Fields**: within each segment, a variable number of fields (1, 4, or 5), each field is a VLQ-encoded integer.
      * 1 field = unmapped (just destination column).
      * 4 fields = mapped (dst col + source id + line + col).
      * 5 fields = mapped + a symbol name.

* **Running totals**: each field is stored as a *delta* from the previous value (generated column resets per line; others carry across).

#### The compression trick

Source maps use **deltas** instead of full values.

Absolute:

```
(0,100,0) (5,100,5) (10,100,10)
src_line: "gB","gB","gB" → 6 chars
```

Delta:

```
(0,100,0) (5,0,5) (5,0,5)
src_line: "gB","A","A"   → 4 chars
```

So repeated fields collapse to tiny encodings, making real maps dramatically smaller.

Note/gotcha: the generated column resets at each new destination line (;). All other fields (source id, original line, original column, name) carry over until changed.

#### Unmapped segments

Tokens with no source mapping are encoded as a single field segment. Though perhaps unintuitive, there are valid reasons for this:

* **Generated code with no origin** (wrappers, helpers, polyfills).
* **Maintain correct spacing** so later mapped tokens line up.
* **Spec consistency** — every segment has at least a generated column field.

### Quick inventory of key terms

* **Destination (dst)**: coordinates in generated code.
* **Source (src)**: coordinates in original code.
* **Token**: one mapping pair (dst → src + optional name).
* **Segment**: encoded representation of a token inside the `mappings` string.
* **Field**: one VLQ-encoded integer; fields can be concatenated into a segment because VLQ is self-delimiting.
* **Mappings string**: semicolon-separated lines of comma-separated segments.
* **Running totals / deltas**: the way each segment encodes its numbers, relative to the last.
