// Copyright 2025 O2Lab
// SPDX-License-Identifier: Apache-2.0

import org.json.XML;
import org.json.JSONException;
import java.nio.charset.StandardCharsets;

public class XmlToJsonFuzzer {
    public static void fuzzerTestOneInput(byte[] data) {
        String input = new String(data, StandardCharsets.UTF_8);
        try {
            XML.toJSONObject(input);
        } catch (JSONException e) {
            // Expected parsing errors - ignore
        }
        // NumberFormatException is NOT caught - will crash fuzzer
    }
}
