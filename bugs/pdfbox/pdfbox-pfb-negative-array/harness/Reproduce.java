import org.apache.fontbox.pfb.PfbParser;
import java.util.Base64;

public class Reproduce {
    public static void main(String[] args) throws Exception {
        byte[] crash = Base64.getDecoder().decode("gAEBAAD/////////JwX4/9JA");
        new PfbParser(crash);  // NegativeArraySizeException: -16777215
    }
}
