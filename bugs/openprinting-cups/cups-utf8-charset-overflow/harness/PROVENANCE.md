# cups-utf8-charset-overflow harness provenance

- **Source**: Issue body of https://github.com/OpenPrinting/cups/issues/1438 — only names the OSS-Fuzz harness `fuzz_transcode` and the OSS-Fuzz reproduce command. No harness source is pasted.
- **URL fragment**: https://github.com/OpenPrinting/cups/issues/1438#issue
- **Found in**: not_found
- **Notes**: The reporter says to reproduce via `python3 infra/helper.py reproduce cups fuzz_transcode poc_crash.bin`. The harness `fuzz_transcode` is part of the OSS-Fuzz CUPS integration (lives in the OpenPrinting/fuzzing repo per bench-corpus.json notes). Source not in the issue.
