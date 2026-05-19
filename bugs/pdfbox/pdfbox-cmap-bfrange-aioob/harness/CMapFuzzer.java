// Adapted from upstream PR #411 Reproduce.java: takes a byte[] directly
// so PocRunner can drive it.
import org.apache.fontbox.cmap.CMapParser;
import org.apache.pdfbox.io.RandomAccessReadBuffer;

public class CMapFuzzer {
    public static void fuzzerTestOneInput(byte[] data) throws Exception {
        CMapParser parser = new CMapParser();
        parser.parse(new RandomAccessReadBuffer(data));
    }
}
