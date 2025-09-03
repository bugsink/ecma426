import json
import unittest
from .vlq import encode_value, encode_values, decode_string
from .model import Token
from .codec import encode_tokens, decode_mappings, encode, decode


class VlqTestCase(unittest.TestCase):
    def roundtrip(self, xs):
        return decode_string(encode_values(xs))

    def test_zero(self):
        self.assertEqual(encode_value(0), "A")
        self.assertEqual(self.roundtrip([0]), [0])

    def test_one_and_minus_one(self):
        self.assertEqual(encode_value(1), "C")   # to_vlq(1)=2 -> 'C'
        self.assertEqual(encode_value(-1), "D")  # to_vlq(-1)=3 -> 'D'
        self.assertEqual(self.roundtrip([1, -1]), [1, -1])

    def test_multi_chunk_boundaries(self):
        # 16 -> to_vlq(16)=32, needs continuation: "gB"
        self.assertEqual(encode_value(16), "gB")
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
        self.assertEqual(encode_value(17), "iB")
        self.assertEqual(decode_string("iB"), [17])
        self.assertEqual(encode_value(-10), "V")
        self.assertEqual(decode_string("V"), [-10])

    def test_known_segment_gaag(self):
        # "GAAG" stands for [3,0,0,3]
        self.assertEqual(encode_values([3, 0, 0, 3]), "GAAG")
        self.assertEqual(decode_string("GAAG"), [3, 0, 0, 3])


class MappingsCodecTests(unittest.TestCase):
    def assert_roundtrip(self, tokens):
        mappings_string, sources_array, names_array = encode_tokens(tokens)
        decoded = decode_mappings(mappings_string, sources_array, names_array)
        self.assertEqual(decoded, tokens)

    def test_empty_roundtrip(self):
        self.assert_roundtrip([])

    def test_single_unmapped_roundtrip(self):
        self.assert_roundtrip([Token(dst_line=0, dst_col=7)])

    def test_single_mapped_no_name_roundtrip(self):
        self.assert_roundtrip([Token(dst_line=0, dst_col=3, src="a.js", src_line=10, src_col=2)])

    def test_single_mapped_with_name_roundtrip(self):
        self.assert_roundtrip([Token(dst_line=0, dst_col=0, src="s.js", src_line=1, src_col=1, name="n")])

    def test_unmapped_line_roundtrip(self):
        self.assert_roundtrip([Token(dst_line=0, dst_col=c) for c in (0, 4, 9)])

    def test_mapped_no_names_deltas_roundtrip(self):
        self.assert_roundtrip([
            Token(dst_line=0, dst_col=0, src="a.js", src_line=10, src_col=0),
            Token(dst_line=0, dst_col=5, src="a.js", src_line=10, src_col=3),
            Token(dst_line=0, dst_col=12, src="a.js", src_line=11, src_col=0),
        ])

    def test_mixed_named_unnamed_roundtrip(self):
        self.assert_roundtrip([
            Token(dst_line=0, dst_col=0,  src="m.js", src_line=0, src_col=0, name="alpha"),
            Token(dst_line=0, dst_col=4,  src="m.js", src_line=0, src_col=3),
            Token(dst_line=0, dst_col=8,  src="m.js", src_line=0, src_col=6, name="beta"),
            Token(dst_line=1, dst_col=0,  src="m.js", src_line=1, src_col=0),
            Token(dst_line=1, dst_col=10, src="m.js", src_line=1, src_col=5, name="gamma"),
        ])

    def test_offsets_across_lines_roundtrip(self):
        self.assert_roundtrip([
            Token(dst_line=0, dst_col=2,  src="s.js", src_line=5, src_col=1, name="n0"),
            Token(dst_line=0, dst_col=9,  src="s.js", src_line=5, src_col=4),
            Token(dst_line=1, dst_col=1,  src="s.js", src_line=6, src_col=0, name="n1"),
            Token(dst_line=1, dst_col=6,  src="s.js", src_line=6, src_col=3),
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
        for token in tokens:
            self.assertEqual(index.lookup(token.dst_line, token.dst_col), token)

    def test_empty(self):
        self.assert_roundtrip([])

    def test_single_line(self):
        self.assert_roundtrip([
            Token(dst_line=0, dst_col=0, src="a.js", src_line=0, src_col=0, name="A"),
            Token(dst_line=0, dst_col=5, src="a.js", src_line=0, src_col=4),
            Token(dst_line=0, dst_col=12),
        ])

    def test_multi_line(self):
        self.assert_roundtrip([
            Token(dst_line=0, dst_col=0),
            Token(dst_line=0, dst_col=6, src="x.js", src_line=1, src_col=2, name="X"),
            Token(dst_line=1, dst_col=0, src="y.js", src_line=10, src_col=0),
            Token(dst_line=1, dst_col=7, src="y.js", src_line=10, src_col=5, name="Y"),
        ])

    def test_strict_types(self):
        with self.assertRaises(TypeError):
            decode({"version": 3, "sources": ["ok", 123], "names": [], "mappings": ""})
        with self.assertRaises(TypeError):
            decode({"version": 3, "sources": [], "names": ["ok", None], "mappings": ""})
        with self.assertRaises(TypeError):
            decode({"version": 3, "sources": [], "names": [], "mappings": 42})

    def test_wrong_version(self):
        with self.assertRaises(ValueError):
            decode({"version": 2, "sources": [], "names": [], "mappings": ""})

    def test_xssi_prefix(self):
        tokens = [Token(dst_line=0, dst_col=3, src="a.js", src_line=10, src_col=2, name="n")]
        payload = ")]}'\n" + json.dumps(encode(tokens))
        index = decode(payload)
        self.assertEqual(list(index), tokens)


class SourceMapIndexLookupTests(unittest.TestCase):
    def build_index(self, tokens_input):
        return decode(encode(tokens_input))

    def test_in_gap_chooses_left(self):
        index = self.build_index([
            Token(dst_line=0, dst_col=0),
            Token(dst_line=0, dst_col=5),
            Token(dst_line=0, dst_col=12),
        ])
        self.assertEqual(index.lookup(0, 7).dst_col, 5)
        self.assertEqual(index.lookup(0, 11).dst_col, 5)

    def test_beyond_last_returns_last(self):
        index = self.build_index([
            Token(dst_line=0, dst_col=2),
            Token(dst_line=0, dst_col=9),
        ])
        self.assertEqual(index.lookup(0, 999).dst_col, 9)

    def test_before_first_raises(self):
        index = self.build_index([
            Token(dst_line=0, dst_col=3),
            Token(dst_line=0, dst_col=10),
        ])
        with self.assertRaises(IndexError):
            index.lookup(0, 0)

    def test_exact_match(self):
        tokens_input = [
            Token(dst_line=1, dst_col=0),
            Token(dst_line=1, dst_col=8),
        ]
        index = self.build_index(tokens_input)
        self.assertEqual(index.lookup(1, 0), tokens_input[0])
        self.assertEqual(index.lookup(1, 8), tokens_input[1])


if __name__ == "__main__":
    unittest.main()
