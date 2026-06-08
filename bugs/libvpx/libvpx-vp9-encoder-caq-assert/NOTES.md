# NOTES — libvpx-vp9-encoder-caq-assert

## The bug
A debug assertion in the VP9 encoder's complexity-adaptive-quantization path
fails on a crafted encoder config:

```
vp9/encoder/vp9_aq_complexity.c:128: vp9_caq_select_segment:
  Assertion `cpi->rc.sb64_target_rate < INT_MAX / 256' failed.
```

The crafted config drives `rc.sb64_target_rate` out of its valid range; the
assert catches it and `abort()`s. A Type-1 finding (the assert guards a real
invalid-state bug).

## Sanitizer fidelity (matches the original discovery tree)
- Build: `clang -fsanitize=address` — **ASan ONLY, no UBSan**.
- libvpx `./configure --enable-debug --disable-optimizations` so the asserts are
  compiled in (NDEBUG off).
- The crash is a plain `assert()` -> `SIGABRT` with **no** sanitizer
  runtime-error trailer. The grader reads the real terminating signal via
  `syscall.WaitStatus` (SIGABRT), so the bare assert-abort is detected.

## Oracle
- class `abrt`, sanitizer `asan`; reach/site keyed to `vp9_aq_complexity.c:128`
  in `vp9_caq_select_segment`; capability_set `[crash, class]`.

## PoC
`poc/poc.bin` is the transferred crash input.
