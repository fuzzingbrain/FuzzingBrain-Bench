#!/usr/bin/env python3
# Rematerialize the 5-byte PoC for the openscreen ANSWER jsoncpp non-object abort.
# (From crash-ae66e334080139a012749a8ab33506595c6530ec.repro/generate_poc.py.)
# Byte 0 = 0x00 (selector mod 5 -> 0 -> AudioConstraints::TryParse).
# Bytes 1..2 = "[]" (jsoncpp parses to arrayValue).
# Bytes 3..4 = trailing pad ignored by jsoncpp.
poc = bytes([0x00, 0x5b, 0x5d, 0x00, 0x05])
open("poc.bin", "wb").write(poc)
print("wrote poc.bin (5 bytes)")
