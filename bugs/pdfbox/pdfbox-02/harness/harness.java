import org.apache.pdfbox.cos.COSDictionary;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.pdmodel.graphics.image.PDInlineImage;

public class InlineImageFuzzer {
    public static void fuzzerTestOneInput(byte[] data) throws Exception {
        COSDictionary params = new COSDictionary();
        params.setInt(COSName.W, 1);
        params.setInt(COSName.H, 1);
        params.setName(COSName.CS, "DeviceRGB");
        params.setInt(COSName.D, 123);  // wrong type: integer instead of array

        PDInlineImage image = new PDInlineImage(params, new byte[]{0, 0, 0}, null);
        image.getDecode();  // ClassCastException
    }
}
