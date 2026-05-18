# ghidra-cplus-demangle-oom harness provenance

- **Source**: Same advisory body as ghidra-rust-demangle-oom (https://github.com/NationalSecurityAgency/ghidra/security/advisories/GHSA-m94m-fqr3-x442). The advisory mentions both `cplus_demangle()` and `rust_demangle()` as affected and shows the fuzz_rust_demangle.c harness (cplus_demangle is reachable via the same demangler entry point with a different mangling style).
- **URL fragment**: GHSA-m94m-fqr3-x442 (advisory body, "Affected Components: rust_demangle(), cplus_demangle()")
- **Found in**: advisory_body
- **Notes**: Same harness as ghidra-rust-demangle-oom; the report does not provide a separate cplus_demangle harness — the listed harness exercises the demangler entry point, which dispatches to either rust_demangle or cplus_demangle internally based on the mangled prefix.
