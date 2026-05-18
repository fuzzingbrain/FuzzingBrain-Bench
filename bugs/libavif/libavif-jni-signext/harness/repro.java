// JNI-surface reproducer from issue body (https://github.com/AOMediaCodec/libavif/issues/3177).
// Constructs an 8-byte direct ByteBuffer with a truncated `ftyp` box header and
// calls AvifDecoder.getInfo(buf, -1, info) to trigger the heap-buffer-overflow.

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
