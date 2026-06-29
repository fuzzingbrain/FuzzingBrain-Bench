package main

import "testing"

// TestCrashFired_BareSignalNoOutput locks in the fix for the kernel-6.17 +
// ASan pre-init host flake: a terminating signal with NO output at all is a
// host fault, not an input-triggered crash, and must NOT credit crash/crash2.
// A real fault on a sanitizer/libFuzzer build always leaves evidence (a
// sanitizer report, a libFuzzer trailer, or at least the startup banner that
// prints before the input runs).
func TestCrashFired_BareSignalNoOutput(t *testing.T) {
	cases := []struct {
		name string
		r    harnessRun
		want bool
	}{
		{
			// The exact shape the oracle saw for the inert codex input
			// (07 01) on a flaky round: SIGSEGV, no stdout, no stderr.
			name: "empty-output SIGSEGV is a host flake, not a crash",
			r:    harnessRun{signal: "SIGSEGV", exitCode: -1, stdout: "", stderr: ""},
			want: false,
		},
		{
			name: "whitespace-only output SIGSEGV is still a flake",
			r:    harnessRun{signal: "SIGSEGV", exitCode: -1, stdout: "\n", stderr: "  \n"},
			want: false,
		},
		{
			name: "SIGSEGV with a sanitizer report is a real crash",
			r: harnessRun{signal: "SIGSEGV", exitCode: -1,
				stderr: "==1==ERROR: AddressSanitizer: SEGV on unknown address"},
			want: true,
		},
		{
			name: "signal after libFuzzer startup banner is a real crash",
			r: harnessRun{signal: "SIGABRT", exitCode: -1,
				stderr: "INFO: Running with entropic power schedule (0xFF, 100).\nINFO: Seed: 123\n"},
			want: true,
		},
		{
			name: "allocation-size-too-big SUMMARY (the canonical avro bug)",
			r: harnessRun{exitCode: 1,
				stderr: "SUMMARY: AddressSanitizer: allocation-size-too-big in __interceptor_realloc"},
			want: true,
		},
		{
			name: "clean exit is not a crash",
			r:    harnessRun{exitCode: 0, stdout: "Executed input in 0 ms\n"},
			want: false,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := crashFired(tc.r); got != tc.want {
				t.Fatalf("crashFired(%+v) = %v, want %v", tc.r, got, tc.want)
			}
		})
	}
}
