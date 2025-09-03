import unittest
from ecma426.vlq import encode_value, encode_values, decode_string


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


if __name__ == "__main__":
    unittest.main()
