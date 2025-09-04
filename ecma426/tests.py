import json
import unittest
from itertools import tee, zip_longest

from .vlq import encode_values, decode_string, _INT_MIN, _INT_MAX
from .model import Mapping
from .codec import encode_mappings, decode_mappings, encode, decode
from . import loads


def shifted_pairs(iterable, fill=None):
    a, b = tee(iterable)
    next(b, None)
    return zip_longest(a, b, fillvalue=fill)


class VlqTestCase(unittest.TestCase):
    def roundtrip(self, xs):
        return decode_string(encode_values(xs))

    def test_zero(self):
        self.assertEqual(encode_values([0]), "A")
        self.assertEqual(self.roundtrip([0]), [0])

    def test_one_and_minus_one(self):
        self.assertEqual(encode_values([1]), "C")   # to_vlq(1)=2 -> 'C'
        self.assertEqual(encode_values([-1]), "D")  # to_vlq(-1)=3 -> 'D'
        self.assertEqual(self.roundtrip([1, -1]), [1, -1])

    def test_multi_chunk_boundaries(self):
        # 16 -> to_vlq(16)=32, needs continuation: "gB"
        self.assertEqual(encode_values([16]), "gB")
        self.assertEqual(self.roundtrip([16]), [16])
        self.assertEqual(self.roundtrip([-16, 32, -33]), [-16, 32, -33])

    def test_sequence_encoding_decoding(self):
        xs = [0, 1, -1, 2, -2, 15, -15, 16, -16, 31, -31, 32, -32, 255, -255]
        s = encode_values(xs)
        self.assertEqual(decode_string(s), xs)

    def test_truncated_raises(self):
        # 'g' has continuation set but no following digit -> truncated
        with self.assertRaises(ValueError):
            decode_string("g")

    def test_identity_sweep_small_range(self):
        xs = list(range(-1000, 1001))
        s = encode_values(xs)
        ys = decode_string(s)
        self.assertEqual(xs, ys)

    def test_known_examples_from_spec(self):
        # ECMA-426 examples: "iB" -> 17, "V" -> -10
        self.assertEqual(encode_values([17]), "iB")
        self.assertEqual(decode_string("iB"), [17])
        self.assertEqual(encode_values([-10]), "V")
        self.assertEqual(decode_string("V"), [-10])

    def test_known_segment_gaag(self):
        # "GAAG" stands for [3,0,0,3]
        self.assertEqual(encode_values([3, 0, 0, 3]), "GAAG")
        self.assertEqual(decode_string("GAAG"), [3, 0, 0, 3])


class VlqSpecialCasesTests(unittest.TestCase):
    def test_decode_min_int_literal(self):
        # ECMA-426 §5.1 “Decode a base64 VLQ”, step 9:
        #   “If value is 0 and sign is -1, return -2147483648.”
        # One-char base64 'B' => first = 1 → sign = -1, value = 0 → _INT_MIN.
        self.assertEqual(decode_string("B"), [_INT_MIN])

    def test_encode_min_int_literal(self):
        # Mirrors §5.1 step 9 special case on the encode side:
        # _INT_MIN must decode from a single byte with sign=-1 and value=0 → base64 'B'.
        self.assertEqual(encode_values([_INT_MIN]), "B")

    def test_encode_rejects_out_of_range(self):
        # ECMA-426 §5.1 step 7.f (decoder):
        #   “If value is greater than or equal to 2^31, throw an error.”
        # Encoder mirrors the same 32-bit bound.
        with self.assertRaises(ValueError):
            encode_values([_INT_MAX + 1])
        with self.assertRaises(ValueError):
            encode_values([_INT_MIN - 1])

    def test_decode_rejects_overflow(self):
        # ECMA-426 §5.1 step 7.f:
        #   “If value is greater than or equal to 2^31, throw an error.”
        # Long run of '/' keeps continuation on and pushes value beyond 2^31.
        with self.assertRaises(ValueError):
            decode_string("////////")

    def test_roundtrip_edge_bounds(self):
        # Within 32-bit range per §5.1/step 7.f bound.
        for v in (0, 1, -1, 15, -15, 16, -16, 31, -31, 2**20, -(2**20), _INT_MIN, _INT_MAX):
            s = encode_values([v])
            self.assertEqual(decode_string(s), [v])


class MappingsCodecTests(unittest.TestCase):
    def assert_roundtrip(self, tokens):
        mappings_string, sources_array, names_array = encode_mappings(tokens)
        decoded = decode_mappings(mappings_string, sources_array, names_array)
        self.assertEqual(decoded, tokens)

    def test_empty_roundtrip(self):
        self.assert_roundtrip([])

    def test_single_unmapped_roundtrip(self):
        self.assert_roundtrip([Mapping(generated_line=0, generated_column=7)])

    def test_single_mapped_no_name_roundtrip(self):
        self.assert_roundtrip([Mapping(generated_line=0, generated_column=3, source="a.js", original_line=10, original_column=2)])

    def test_single_mapped_with_name_roundtrip(self):
        self.assert_roundtrip([Mapping(generated_line=0, generated_column=0, source="s.js", original_line=1, original_column=1, name="n")])

    def test_unmapped_line_roundtrip(self):
        self.assert_roundtrip([Mapping(generated_line=0, generated_column=c) for c in (0, 4, 9)])

    def test_mapped_no_names_deltas_roundtrip(self):
        self.assert_roundtrip([
            Mapping(generated_line=0, generated_column=0, source="a.js", original_line=10, original_column=0),
            Mapping(generated_line=0, generated_column=5, source="a.js", original_line=10, original_column=3),
            Mapping(generated_line=0, generated_column=12, source="a.js", original_line=11, original_column=0),
        ])

    def test_mixed_named_unnamed_roundtrip(self):
        self.assert_roundtrip([
            Mapping(generated_line=0, generated_column=0,  source="m.js", original_line=0, original_column=0, name="alpha"),
            Mapping(generated_line=0, generated_column=4,  source="m.js", original_line=0, original_column=3),
            Mapping(generated_line=0, generated_column=8,  source="m.js", original_line=0, original_column=6, name="beta"),
            Mapping(generated_line=1, generated_column=0,  source="m.js", original_line=1, original_column=0),
            Mapping(generated_line=1, generated_column=10, source="m.js", original_line=1, original_column=5, name="gamma"),
        ])

    def test_offsets_across_lines_roundtrip(self):
        self.assert_roundtrip([
            Mapping(generated_line=0, generated_column=2,  source="s.js", original_line=5, original_column=1, name="n0"),
            Mapping(generated_line=0, generated_column=9,  source="s.js", original_line=5, original_column=4),
            Mapping(generated_line=1, generated_column=1,  source="s.js", original_line=6, original_column=0, name="n1"),
            Mapping(generated_line=1, generated_column=6,  source="s.js", original_line=6, original_column=3),
        ])

    def test_decode_rejects_empty_segment(self):
        with self.assertRaises(ValueError):
            decode_mappings(",", [], [])

    def test_decode_rejects_two_field_segment(self):
        with self.assertRaises(ValueError):
            decode_mappings("AA", [], [])


class JsonCodecTests(unittest.TestCase):

    def assert_roundtrip(self, tokens):
        sourcemap_dict = encode(tokens)
        index = decode(sourcemap_dict)
        self.assertEqual(list(index), tokens)
        # check that the index was built correctly as part of the decode step
        for token in tokens:
            self.assertEqual(index[(token.generated_line, token.generated_column)], token)

    def test_empty(self):
        self.assert_roundtrip([])

    def test_single_line(self):
        self.assert_roundtrip([
            Mapping(generated_line=0, generated_column=0, source="a.js", original_line=0, original_column=0, name="A"),
            Mapping(generated_line=0, generated_column=5, source="a.js", original_line=0, original_column=4),
            Mapping(generated_line=0, generated_column=12),
        ])

    def test_multi_line(self):
        self.assert_roundtrip([
            Mapping(generated_line=0, generated_column=0),
            Mapping(generated_line=0, generated_column=6, source="x.js", original_line=1, original_column=2, name="X"),
            Mapping(generated_line=1, generated_column=0, source="y.js", original_line=10, original_column=0),
            Mapping(generated_line=1, generated_column=7, source="y.js", original_line=10, original_column=5, name="Y"),
        ])

    def test_strict_types(self):
        with self.assertRaises(TypeError):
            decode({"version": 3, "sources": ["ok", 123], "names": [], "mappings": ""})
        with self.assertRaises(TypeError):
            decode({"version": 3, "sources": [], "names": ["ok", None], "mappings": ""})
        with self.assertRaises(TypeError):
            decode({"version": 3, "sources": [], "names": [], "mappings": 42})

    def test_null_source(self):
        decode({"version": 3, "sources": [None], "names": [], "mappings": ""})

    def test_wrong_version(self):
        with self.assertRaises(ValueError):
            decode({"version": 2, "sources": [], "names": [], "mappings": ""})

    def test_loads_xssi_prefix(self):
        tokens = [Mapping(generated_line=0, generated_column=3, source="a.js", original_line=10, original_column=2, name="n")]
        payload = ")]}'\n" + json.dumps(encode(tokens))
        index = loads(payload)
        self.assertEqual(list(index), tokens)


class SourceMapIndexLookupTests(unittest.TestCase):
    def build_index(self, tokens_input):
        return decode(encode(tokens_input))

    def test_in_gap_chooses_left(self):
        index = self.build_index([
            Mapping(generated_line=0, generated_column=0),
            Mapping(generated_line=0, generated_column=5),
            Mapping(generated_line=0, generated_column=12),
        ])
        self.assertEqual(index.lookup_left(0, 7).generated_column, 5)
        self.assertEqual(index.lookup_left(0, 11).generated_column, 5)

    def test_beyond_last_returns_last(self):
        index = self.build_index([
            Mapping(generated_line=0, generated_column=2),
            Mapping(generated_line=0, generated_column=9),
        ])
        self.assertEqual(index.lookup_left(0, 999).generated_column, 9)

    def test_before_first_raises(self):
        index = self.build_index([
            Mapping(generated_line=0, generated_column=3),
            Mapping(generated_line=0, generated_column=10),
        ])
        with self.assertRaises(IndexError):
            index.lookup_left(0, 0)

    def test_exact_match(self):
        tokens_input = [
            Mapping(generated_line=1, generated_column=0),
            Mapping(generated_line=1, generated_column=8),
        ]
        index = self.build_index(tokens_input)
        self.assertEqual(index.lookup_left(1, 0), tokens_input[0])
        self.assertEqual(index.lookup_left(1, 8), tokens_input[1])


class IndexMapTests(unittest.TestCase):
    def test_two_sections_flatten_offsets(self):
        # section 1 (no offset)
        s1_tokens = [
            Mapping(generated_line=0, generated_column=0, source="a.js", original_line=0, original_column=0, name="A"),
            Mapping(generated_line=0, generated_column=5, source="a.js", original_line=0, original_column=4),
            Mapping(generated_line=1, generated_column=0),
        ]
        s1_map = encode(s1_tokens)

        # section 2 (line=100, column=10); column offset applies only to first line
        s2_tokens = [
            Mapping(generated_line=0, generated_column=1, source="b.js", original_line=0, original_column=0, name="B"),
            Mapping(generated_line=1, generated_column=2, source="b.js", original_line=1, original_column=0),
        ]
        s2_map = encode(s2_tokens)

        index_map = {
            "version": 3,
            "file": "bundle.js",
            "sections": [
                {"offset": {"line": 0, "column": 0}, "map": s1_map},
                {"offset": {"line": 100, "column": 10}, "map": s2_map},
            ],
        }

        idx = decode(index_map)

        expected = [
            # s1 unchanged (offset 0,0)
            *s1_tokens,
            # s2 with offsets applied: +100 lines; +10 column on first line only
            Mapping(generated_line=100, generated_column=11, source="b.js", original_line=0, original_column=0, name="B"),
            Mapping(generated_line=101, generated_column=2,  source="b.js", original_line=1, original_column=0),
        ]
        self.assertEqual(list(idx), expected)

        # exact lookups prove index constructed
        for t in expected:
            self.assertEqual(idx[(t.generated_line, t.generated_column)], t)

    def test_empty_sections(self):
        index_map = {"version": 3, "sections": []}
        idx = decode(index_map)
        self.assertEqual(list(idx), [])

    def test_sections_must_be_list(self):
        with self.assertRaises(TypeError):
            decode({"version": 3, "sections": {}})

    def test_section_must_be_object(self):
        with self.assertRaises(TypeError):
            decode({"version": 3, "sections": [42]})

    def test_offset_shape(self):
        bad1 = {"version": 3, "sections": [{"offset": {}, "map": encode([])}]}
        bad2 = {"version": 3, "sections": [{"offset": {"line": "0", "column": 0}, "map": encode([])}]}
        bad3 = {"version": 3, "sections": [{"offset": {"line": 0}, "map": encode([])}]}
        for m in (bad1, bad2, bad3):
            with self.assertRaises(TypeError):
                decode(m)

    def test_map_must_be_object(self):
        with self.assertRaises(TypeError):
            decode({"version": 3, "sections": [{"offset": {"line": 0, "column": 0}, "map": 123}]})

    def test_sections_sorted_and_non_overlapping(self):
        # same start as previous → invalid (must be strictly increasing by (line, column))
        s = encode([Mapping(generated_line=0, generated_column=0)])
        index_map = {
            "version": 3,
            "sections": [
                {"offset": {"line": 10, "column": 5}, "map": s},
                {"offset": {"line": 10, "column": 5}, "map": s},
            ],
        }
        with self.assertRaises(ValueError):
            decode(index_map)

        # earlier start than previous → invalid
        index_map2 = {
            "version": 3,
            "sections": [
                {"offset": {"line": 20, "column": 0}, "map": s},
                {"offset": {"line": 19, "column": 10}, "map": s},
            ],
        }
        with self.assertRaises(ValueError):
            decode(index_map2)

    def test_embedded_regular_map_field_types(self):
        # names entry not string
        m1 = encode([Mapping(generated_line=0, generated_column=0)])
        m1["names"] = ["ok", 123]
        idx_map = {"version": 3, "sections": [{"offset": {"line": 0, "column": 0}, "map": m1}]}
        with self.assertRaises(TypeError):
            decode(idx_map)

        # mappings not string
        m2 = encode([Mapping(generated_line=0, generated_column=0)])
        m2["mappings"] = 42
        idx_map = {"version": 3, "sections": [{"offset": {"line": 0, "column": 0}, "map": m2}]}
        with self.assertRaises(TypeError):
            decode(idx_map)


class CaptureExceptionMapIntegrationTests(unittest.TestCase):

    # MIN_JS and MAP taken from
    # https://github.com/bugsink/event-samples/blob/main/bugsink/artifact_bundles/51a5a327666cf1d11e23adfd55c3becad27ae769.zip

    MIN_JS = """
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="9b7990f8-1f25-571a-a422-03bea91eb8ab")}catch(e){}}();
function bar(){Sentry.captureException(new Error("Sentry Test Error"))}function foo(){bar()}function captureException(){foo()}
//# sourceMappingURL=captureException.min.js.map
//# debugId=9b7990f8-1f25-571a-a422-03bea91eb8ab""" # noqa

    MAP = r"""{"version":3,"sources":["captureException.js"],"sourcesContent":["\n\n\n\n\nfunction bar() {\n    Sentry.captureException(new Error(\"Sentry Test Error\"));\n}\n\nfunction foo() {\n    bar();\n}\n\nfunction captureException() {\n    foo();\n}\n"],"names":["bar","Sentry","captureException","Error","foo"],"mappings":";;AAKA,SAASA,MACLC,OAAOC,iBAAiB,IAAIC,MAAM,mBAAmB,CAAC,CAC1D,CAEA,SAASC,MACLJ,IAAI,CACR,CAEA,SAASE,mBACLE,IAAI,CACR","debug_id":"9b7990f8-1f25-571a-a422-03bea91eb8ab"}""" # noqa

    def _display(self, lines, start_line, start_col, end_line, end_col):
        """Extract substr from (start_line, start_col) up to (end_line, end_col); the quick & dirty way (no checks)."""

        if start_line == end_line:
            return lines[start_line][start_col:end_col]

        parts = [lines[start_line][start_col:]]
        parts.extend(lines[start_line + 1:end_line])
        parts.append(lines[end_line][:end_col])

        return "\n".join(parts)

    def test_decode_and_probe_named_tokens(self):
        def _min(s):
            return s.replace(" ", "").replace("\n", "").replace(";", "")

        index = loads(self.MAP)
        tokens = list(index)

        original = index.raw["sourcesContent"][0].splitlines()
        min_js = self.MIN_JS.splitlines()

        for token, next_token in shifted_pairs(tokens):
            if not next_token:
                continue  # slightly less complete test but not worth the effort

            self.assertEqual(
                _min(self._display(min_js, token.generated_line, token.generated_column, next_token.generated_line, next_token.generated_column)),
                _min(self._display(original, token.original_line, token.original_column, next_token.original_line, next_token.original_column)))


class StrictIndexingTests(unittest.TestCase):
    def build_index(self, tokens_input):
        return decode(encode(tokens_input))

    def test_exact_indexing_succeeds(self):
        t0 = Mapping(generated_line=1, generated_column=3)
        idx = self.build_index([t0])
        self.assertEqual(idx[(1, 3)], t0)

    def test_indexing_missing_raises_keyerror(self):
        t0 = Mapping(generated_line=1, generated_column=3)
        idx = self.build_index([t0])
        with self.assertRaises(KeyError):
            _ = idx[(1, 2)]  # in-gap → strict lookup fails


if __name__ == "__main__":
    unittest.main()
