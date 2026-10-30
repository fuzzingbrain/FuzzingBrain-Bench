import java.io.IOException;
import org.apache.fontbox.pfb.PfbParser;

public class PfbFuzzer {
    public static void fuzzerTestOneInput(byte[] data) throws Exception {
        // Jazzer-style harness: IOException is PfbParser's DECLARED "malformed font"
        // rejection, so it is a clean parse failure, not a finding. Only an undeclared



        try {
            new PfbParser(data);
        } catch (IOException expected) {
            // malformed input rejected cleanly
        }
    }
}
