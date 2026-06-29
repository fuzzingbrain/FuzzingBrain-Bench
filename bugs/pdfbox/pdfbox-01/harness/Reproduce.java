import org.apache.fontbox.cmap.CMap;
import org.apache.fontbox.cmap.CMapParser;
import org.apache.pdfbox.io.RandomAccessReadBuffer;

public class Reproduce {
    public static void main(String[] args) throws Exception {
        byte[] cmapData = "1 beginbfrange\n<> <> <2223>\nendbfrange"
                .getBytes("US-ASCII");
        CMapParser parser = new CMapParser();
        CMap cmap = parser.parse(new RandomAccessReadBuffer(cmapData));
        // ArrayIndexOutOfBoundsException: Index -1 out of bounds for length 0
    }
}
