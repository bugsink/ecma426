# vlq.py — ECMA-426 “Decode a base64 VLQ” implementation (decoder)
# Spec (ECMA-426, 1.0): https://426.ecma-international.org/1.0/index.html#decode-a-base64-vlq

# Base64 alphabet (spec’s “[base64] encoding” for code units)
_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_FROM_B64 = {c: i for i, c in enumerate(_B64_ALPHABET)}
_TO_B64 = {i: c for i, c in enumerate(_B64_ALPHABET)}

# Bit masks/constants used in the spec text
_CONT = 0x20  # continuation bit (currentByte & 0x20)
_MASK5 = 0x1F  # low 5 bits (currentByte & 0x1F)
_LIMIT = 1 << 31  # 2^31 (bound check for value during accumulation)
_INT_MIN = -2147483648
_INT_MAX = 2147483647


def decode_string(segment: str) -> list[int]:
    """Decode all Base64 VLQs contained in `segment` (ECMA-426 §5.1)."""
    values = []
    position = 0
    n = len(segment)

    while True:
        # 1) If position points to the end of segment, return null.
        #    (Here: done decoding; return accumulated list.)
        if position >= n:
            return values

        # 2) Let first be a byte whose the value is the number corresponding to
        #    segment’s positionth code unit, according to the [base64] encoding.
        first = _FROM_B64.get(segment[position])
        if first is None:
            raise ValueError(f"invalid base64 digit: {segment[position]!r}")

        # NOTE (spec): The two most significant bits of first are 0.

        # 3) Let sign be 1 if first & 0x01 is 0x00, and -1 otherwise.
        sign = 1 if (first & 0x01) == 0x00 else -1

        # 4) Let value be (first >> 1) & 0x0F, as a number.
        value = (first >> 1) & 0x0F

        # 5) Let nextShift be 16.
        nextShift = 16

        # 6) Let currentByte be first.
        currentByte = first

        # 7) While currentByte & 0x20 is 0x20:
        while (currentByte & _CONT) == _CONT:
            # 7.a) Advance position by 1.
            position += 1

            # 7.b) If position points to the end of segment, throw an error.
            if position >= n:
                raise ValueError("unterminated VLQ (unexpected end of segment)")

            # 7.c) Set currentByte to the byte whose the value is the number
            #      corresponding to segment’s positionth code unit, according to the [base64] encoding.
            currentByte = _FROM_B64.get(segment[position])
            if currentByte is None:
                raise ValueError(f"invalid base64 digit: {segment[position]!r}")

            # 7.d) Let chunk be currentByte & 0x1F, as a number.
            chunk = currentByte & _MASK5

            # 7.e) Add chunk * nextShift to value.
            value += chunk * nextShift

            # 7.f) If value is greater than or equal to 2^31, throw an error.
            if value >= _LIMIT:
                raise ValueError("VLQ value exceeds 32-bit range (>= 2^31)")

            # 7.g) Multiply nextShift by 32.
            nextShift *= 32

        # 8) Advance position by 1.
        position += 1

        # 9) If value is 0 and sign is -1, return -2147483648.
        # NOTE (spec): -2147483648 is the smallest 32-bit signed integer.
        if value == 0 and sign == -1:
            values.append(_INT_MIN)
            continue

        # 10) Return value * sign.
        values.append(value * sign)


def encode_values(values) -> str:
    """
    Encode an iterable of 32-bit signed integers as Base64 VLQ digits (ECMA-426).
    This is the inverse of §5.1 “Decode a base64 VLQ”.

    Invariants mirrored from the spec:
      - Values are 32-bit (decoder step 7.f bound).
      - The first digit contains: sign bit in LSB; 4 value bits (decoder steps 3–4).
      - Continuation uses bit 5 (decoder step 7: currentByte & 0x20).
      - Special case: when decoding sees value==0 and sign==-1, it returns −2147483648 (step 9);
        we encode that value back as a single digit with sign=1 (negative) and value=0.
    """
    out = []

    for n in values:
        # Bound check (mirror decoder step 7.f: disallow values with magnitude >= 2^31)
        if n < _INT_MIN or n > _INT_MAX:
            raise ValueError("VLQ value out of 32-bit range")

        # Special case (decoder step 9): _INT_MIN <-> single digit with sign bit = 1 and value = 0
        if n == _INT_MIN:
            # first = (low4 << 1) | sign ; low4 = 0, sign=1 ⇒ first=1 ⇒ 'B'
            out.append(_TO_B64[1])
            continue

        # Sign & magnitude (decoder steps 3–4 inverted)
        negative = n < 0
        value = -n if negative else n

        # First digit: low 4 bits + sign in bit 0 (decoder steps 3–4)
        low4 = value & 0x0F
        value >>= 4

        first = (low4 << 1) | (1 if negative else 0)

        # If more bits remain, set continuation bit (decoder step 7 condition)
        if value:
            first |= _CONT

        out.append(_TO_B64[first])

        # Continuation digits: 5-bit chunks, least-significant first (decoder step 7.d/e/g)
        while value:
            chunk = value & _MASK5
            value >>= 5
            if value:
                chunk |= _CONT
            out.append(_TO_B64[chunk])

    return "".join(out)
