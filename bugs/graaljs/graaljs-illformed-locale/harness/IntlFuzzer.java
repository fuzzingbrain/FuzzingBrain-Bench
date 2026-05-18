// IntlFuzzer.java
import com.code_intelligence.jazzer.api.FuzzedDataProvider;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.PolyglotException;

public class IntlFuzzer {
    private static Context context;

    static {
        context = Context.newBuilder("js")
            .allowAllAccess(false)
            .option("engine.WarnInterpreterOnly", "false")
            .build();
    }

    public static void fuzzerTestOneInput(FuzzedDataProvider data) {
        String locale = data.consumeRemainingAsString();
        if (locale.isEmpty()) return;

        String jsCode = String.format("new Intl.Locale('%s');", escapeForJS(locale));

        try {
            context.eval("js", jsCode);
        } catch (PolyglotException e) {
            if (e.isInternalError()) {
                // BUG: User input should not cause internal error!
                throw new RuntimeException("Internal error from user input", e);
            }
        }
    }

    private static String escapeForJS(String s) {
        StringBuilder sb = new StringBuilder();
        for (char c : s.toCharArray()) {
            switch (c) {
                case '\\': sb.append("\\\\"); break;
                case '\'': sb.append("\\'"); break;
                case '\n': sb.append("\\n"); break;
                default:
                    if (c >= 32 && c < 127) sb.append(c);
                    else sb.append(String.format("\\u%04x", (int) c));
            }
        }
        return sb.toString();
    }
}
