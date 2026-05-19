// Adapted from upstream PR #3625 'Trigger Method 2: Fuzzer' for the
// FuzzingBrain bench runner: the harness takes a raw byte[] (rather than
// Jazzer's FuzzedDataProvider) so PocRunner can drive it directly without
// pulling in the Jazzer api jar. Logic is otherwise identical.
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
