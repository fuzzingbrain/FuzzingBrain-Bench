// Copyright 2025 O2Lab
// SPDX-License-Identifier: Apache-2.0

import org.json.JSONML;
import org.json.JSONException;
import java.nio.charset.StandardCharsets;

public class JsonMLFuzzer {
    public static void fuzzerTestOneInput(byte[] data) {
        String input = new String(data, StandardCharsets.UTF_8);
        try {
            JSONML.toJSONArray(input);
        } catch (JSONException e) {
            // Expected parsing errors - ignore
        }
        // ClassCastException is NOT caught - will crash fuzzer
    }
}
