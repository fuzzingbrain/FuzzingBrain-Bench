"""Resource-exhaustion crashes sign the same way wherever the resource ran out.

The grader runs every candidate three times and counts it only if all three
runs sign identically. A stack overflow's top frames are wherever the guard
page fell and a JVM OutOfMemoryError's are whichever allocation crossed the
limit, so before this rule one input reproducing the same fault three times
could fail that check (`flaky_location`), or pass it under a different name on
another input and count again. The live evidence is in the commit message; this
file pins the property on synthetic traces of the same shapes.
"""
from fbbench.grading.signature import SIG_VERSION, signature

IM_CYCLE = [("AcquireExceptionInfo", "exception.c:122"),
            ("AcquireSemaphoreInfo", "semaphore.c:203"),
            ("NewLinkedList", "linked-list.c:747"),
            ("InitializeExceptionInfo", "exception.c:740")]


def _native_overflow(offset: int, top: str = "AcquireCriticalMemory", depth: int = 246) -> dict:
    """An ASan stack-overflow report: one frame where the guard page fell, then
    the recursion cycle entered at `offset`, truncated like ASan truncates it."""
    lines = [f"    #0 0x55 in {top} /src/im/memory.c:1:1"]
    for i in range(1, depth):
        func, loc = IM_CYCLE[(i + offset) % len(IM_CYCLE)]
        lines.append(f"    #{i} 0x55 in {func} /src/im/MagickCore/{loc}:5")
    return {"exit_code": 1, "signal": "",
            "stderr": "==1==ERROR: AddressSanitizer: stack-overflow on address 0x7ff\n"
                      + "\n".join(lines) + "\nSUMMARY: AddressSanitizer: stack-overflow",
            "stdout": ""}


def test_a_stack_overflow_signs_the_same_wherever_the_stack_ran_out():
    sigs = {signature(_native_overflow(k, top)).canon_sig
            for k in range(len(IM_CYCLE))
            for top in ("AcquireCriticalMemory", "AcquireMagickMemory", "ResizeQuantumMemory")}
    assert len(sigs) == 1, sigs


def test_it_is_named_by_the_functions_the_recursion_repeats():
    s = signature(_native_overflow(0))
    assert s.canon_sig == ("stack-overflow|AcquireExceptionInfo|AcquireSemaphoreInfo|"
                           "InitializeExceptionInfo")
    assert s.version == SIG_VERSION == 5


def test_a_function_recursing_into_itself_signs_by_itself():
    """opencv-01: parseValue calls parseValue 245 frames deep, and the one frame
    above it is different every run (reserveNodeSpace, convertToCollection,
    FileNode::FileNode). Consecutive repeats must count as repeats here."""
    def run(top):
        lines = [f"    #0 0x55 in {top} /src/opencv/persistence.cpp:1500"]
        lines += [f"    #{i} 0x55 in cv::YAMLParser::parseValue(char*, cv::FileNode&, int, bool) "
                  f"/src/opencv/persistence_yml.cpp:{697 if i % 2 else 659}:17" for i in range(1, 246)]
        return {"exit_code": 1, "signal": "", "stdout": "",
                "stderr": "ERROR: AddressSanitizer: stack-overflow on address 0x7ffe\n"
                          + "\n".join(lines) + "\nSUMMARY: AddressSanitizer: stack-overflow"}
    sigs = {signature(run(t)).canon_sig for t in (
        "cv::FileStorage::Impl::reserveNodeSpace(cv::FileNode&, unsigned long)",
        "cv::FileStorage::Impl::convertToCollection(int, cv::FileNode&)",
        "cv::FileNode::FileNode()")}
    assert sigs == {"stack-overflow|cv::YAMLParser::parseValue"}


def test_a_different_recursion_is_still_a_different_crash():
    other = [("xmlParseElement", "parser.c:1"), ("xmlParseContent", "parser.c:2")]
    lines = [f"    #{i} 0x55 in {other[i % 2][0]} /src/{other[i % 2][1]}:1" for i in range(200)]
    run = {"exit_code": 1, "signal": "", "stdout": "",
           "stderr": "ERROR: AddressSanitizer: stack-overflow\n" + "\n".join(lines)
                     + "\nSUMMARY: AddressSanitizer: stack-overflow"}
    assert signature(run).canon_sig != signature(_native_overflow(0)).canon_sig


def _java(exc: str, frames: list[str]) -> dict:
    body = "\n".join(f"\tat {f}(X.java:{i + 1})" for i, f in enumerate(frames))
    return {"exit_code": 1, "signal": "", "stdout": "",
            "stderr": f'Exception in thread "main" {exc}: Java heap space\n{body}\n'}


def test_a_java_oom_counts_once_wherever_the_heap_ran_out():
    """json-java-01: one input ran out in JSONArray.put, XMLTokener.nextContent,
    or before the library ran at all (only JDK and harness frames)."""
    rounds = [["java.util.HashMap.resize", "org.json.JSONObject.put", "org.json.JSONML.toJSONArray"],
              ["org.json.XMLTokener.nextContent", "org.json.JSONML.toJSONArray"],
              ["java.nio.file.Files.readAllBytes", "PocRunner.main"],
              []]
    sigs = {signature(_java("java.lang.OutOfMemoryError", r)).canon_sig for r in rounds}
    assert sigs == {"java.lang.outofmemoryerror|<no-frames>"}


def test_other_java_exceptions_keep_their_frames():
    a = _java("java.lang.NumberFormatException", ["org.json.XMLTokener.unescapeEntity", "org.json.XML.parse"])
    assert signature(a).canon_sig == ("java.lang.numberformatexception|org.json.XMLTokener.unescapeEntity|"
                                      "org.json.XML.parse")


def test_a_java_stack_overflow_is_named_by_its_cycle():
    cyc = ["org.apache.pdfbox.cos.COSDictionary.getDictionaryObject",
           "org.apache.pdfbox.pdmodel.PDPageTree.get", "org.apache.pdfbox.pdmodel.PDPageTree.getKids"]
    runs = [_java("java.lang.StackOverflowError", [cyc[(i + k) % 3] for i in range(1024)])
            for k in range(3)]
    assert len({signature(r).canon_sig for r in runs}) == 1


def test_other_classes_are_untouched():
    run = {"exit_code": 1, "signal": "", "stdout": "",
           "stderr": "ERROR: AddressSanitizer: heap-buffer-overflow\n"
                     "    #0 0x49 in __interceptor_memcpy compiler-rt/asan.cpp:8\n"
                     "    #1 0x51 in png_handle_iCCP /src/libpng/pngrutil.c:1447:5\n"
                     "    #2 0x52 in png_read_info /src/libpng/pngread.c:123:7\n"
                     "SUMMARY: AddressSanitizer: heap-buffer-overflow"}
    assert signature(run).canon_sig == "heap-buffer-overflow|png_handle_iCCP|png_read_info"
    oom = {"exit_code": 71, "signal": "", "stdout": "",
           "stderr": "ERROR: libFuzzer: out-of-memory (used: 257Mb; limit: 256Mb)\n"
                     "    #0 0x55 in __interceptor_realloc (/h+0xe6026)\n"
                     "    #1 0x55 in str_buf_reserve /src/rust-demangle.c:1553:21\n"
                     "    #2 0x55 in str_buf_append /src/rust-demangle.c:1572:3\n"
                     "SUMMARY: libFuzzer: out-of-memory"}
    assert signature(oom).canon_sig == "out-of-memory|str_buf_reserve|str_buf_append"


def test_every_arm_scores_with_these_rules():
    """The api arm mounted the checkout's rules; the agent arms graded with the
    copy baked into the images. One rule set for everyone, from the sandbox."""
    import inspect
    from fbbench.runner import mcp_client
    from fbbench.sandbox import SIG_RULES, sandbox_args
    args = sandbox_args()
    assert any(a.startswith("BENCH_SIG_SCRIPT=") for a in args)
    assert any(a.startswith(SIG_RULES + ":") for a in args)
    # and the grading client no longer adds its own copy on top
    assert "sig_rules_args()" not in inspect.getsource(mcp_client.MCPClient.__init__)
