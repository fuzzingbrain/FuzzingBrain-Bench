import org.apache.fontbox.cmap.CMapParser;
import org.apache.pdfbox.io.RandomAccessReadBuffer;

public class CMapFuzzer {
    public static void fuzzerTestOneInput(byte[] data) throws Exception {
        CMapParser parser = new CMapParser();
        parser.parse(new RandomAccessReadBuffer(data));
    }
}
