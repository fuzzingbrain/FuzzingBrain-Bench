import org.apache.avro.file.DataFileReader;
import org.apache.avro.file.SeekableByteArrayInput;
import org.apache.avro.generic.GenericDatumReader;
import org.apache.avro.generic.GenericRecord;

public class DecompressionBombFuzzer {
    public static void fuzzerTestOneInput(byte[] input) {
        if (input.length < 32) return;
        try {
            SeekableByteArrayInput sin = new SeekableByteArrayInput(input);
            GenericDatumReader<GenericRecord> reader = new GenericDatumReader<>();
            try (DataFileReader<GenericRecord> fileReader = new DataFileReader<>(sin, reader)) {
                while (fileReader.hasNext()) {
                    fileReader.next();
                }
            }
        } catch (OutOfMemoryError e) {
            throw e;
        } catch (Exception e) {
            // Ignore parse errors
        }
    }
}
