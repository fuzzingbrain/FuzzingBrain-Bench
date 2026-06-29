import java.nio.ByteBuffer;

public class repro {
    public static void main(String[] args) {
        ByteBuffer buf = ByteBuffer.allocateDirect(8);
        buf.putInt(16);
        buf.put((byte) 'f');
        buf.put((byte) 't');
        buf.put((byte) 'y');
        buf.put((byte) 'p');
        buf.flip();

        org.aomedia.avif.android.AvifDecoder.Info info =
            new org.aomedia.avif.android.AvifDecoder.Info();
        org.aomedia.avif.android.AvifDecoder.getInfo(buf, -1, info);
    }
}
