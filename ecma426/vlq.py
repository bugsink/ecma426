# ECMA-426 source maps — Base64 VLQ
# Spec gist:
# - Integers are mapped with ZigZag: to_vlq(n) = (abs(n) << 1) | (n < 0)
# - Stream is 5-bit chunks, LSB-first. If more bits follow, set continuation bit (0b100000).
# - Each 6-bit digit is encoded with base64 alphabet: A-Z a-z 0-9 + /
# - Decoding collects digits until a digit without continuation bit is seen, then ZigZag-unmaps.

_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_TO_B64 = {i: ch for i, ch in enumerate(_B64_ALPHABET)}
_FROM_B64 = {ch: i for i, ch in enumerate(_B64_ALPHABET)}

_CONT = 0b100000
_MASK5 = 0b11111


def _to_vlq(n: int) -> int:
    # Safe zigzag for Python: non-negatives get LSB 0; negatives get LSB 1.
    # (abs(n) << 1) | 1_if_negative
    return (abs(n) << 1) | (1 if n < 0 else 0)


def _from_vlq(v: int) -> int:
    sign = v & 1
    mag = v >> 1
    return -mag if sign else mag


def encode_values(values) -> str:
    """Encode an iterable of ints to a Base64 VLQ string (ECMA-426)."""
    out_chars = []
    for n in values:
        v = _to_vlq(int(n))
        # always emit at least one digit
        while True:
            digit = v & _MASK5
            v >>= 5
            if v:
                digit |= _CONT
            out_chars.append(_TO_B64[digit])
            if not v:
                break
    return "".join(out_chars)


def encode_value(n: int) -> str:
    """Encode a single int to Base64 VLQ."""
    return encode_values([n])


def decode_string(s: str) -> list[int]:
    """Decode a Base64 VLQ string to a list of ints. Raises ValueError on malformed input."""
    vals = []
    acc = 0
    shift = 0
    for ch in s:
        try:
            digit = _FROM_B64[ch]
        except KeyError:
            raise ValueError(f"invalid base64 digit: {ch!r}") from None

        acc |= (digit & _MASK5) << shift
        if digit & _CONT:
            shift += 5
            # continue accumulating
        else:
            vals.append(_from_vlq(acc))
            acc = 0
            shift = 0

    if shift != 0:
        # ended with dangling continuation
        raise ValueError("truncated VLQ sequence")
    return vals
