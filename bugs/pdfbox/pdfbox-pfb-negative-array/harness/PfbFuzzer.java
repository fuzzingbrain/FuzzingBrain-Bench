// Adapted from upstream PR #412 Reproduce.java: takes a byte[] directly
// so PocRunner can drive it.
import java.io.IOException;
import org.apache.fontbox.pfb.PfbParser;

public class PfbFuzzer {
    public static void fuzzerTestOneInput(byte[] data) throws Exception {
        // Jazzer-style harness: IOException is PfbParser's DECLARED "malformed font"
        // rejection, so it is a clean parse failure, not a finding. Only an undeclared
        // RuntimeException (the bug, e.g. NegativeArraySizeException) is a real crash.
        // This makes the crash2 patch-differential well-defined: the vuln throws the
        // RuntimeException (crash), a correct fix throws IOException (caught, clean exit).
        try {
            new PfbParser(data);
        } catch (IOException expected) {
            // malformed input rejected cleanly
        }
    }
}
