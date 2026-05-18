import com.code_intelligence.jazzer.api.FuzzedDataProvider;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.PolyglotException;

public class RegExpFuzzer {
    private static Context context;

    static {
        context = Context.newBuilder("js")
            .allowAllAccess(false)
            .option("engine.WarnInterpreterOnly", "false")
            .build();
    }

    public static void fuzzerTestOneInput(FuzzedDataProvider data) {
        String pattern = data.consumeString(200);
        boolean useVFlag = data.consumeBoolean();
        if (pattern.isEmpty()) return;

        String flags = useVFlag ? "v" : "";
        String jsCode = String.format("try { new RegExp('%s', '%s'); } catch(e) {}",
                                      escapeForJS(pattern), flags);
        try {
            context.eval("js", jsCode);
        } catch (PolyglotException e) {
            if (e.isInternalError()) {
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
                    if (c < 32 || c > 126) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        return sb.toString();
    }
}
