#!/usr/bin/env python3
"""Generate PoC for pdfbox-inlineimage-type-confusion.

The bug is reached programmatically (the harness builds a COSDictionary
with /D set to an integer instead of an array). The byte[] input is
unused; this file exists only because the bench expects every bug to
ship a poc.bin alongside its harness.
"""

def create_poc(output='poc.bin'):
    blob = b''
    with open(output, 'wb') as f:
        f.write(blob)
    print(f"wrote {output} ({len(blob)} bytes, sentinel — harness ignores input)")


if __name__ == '__main__':
    create_poc()
