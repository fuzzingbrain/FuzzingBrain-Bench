package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"syscall"
	"time"
)

// reachFired runs the PoC against the coverage build and uses `llvm-cov
// export` to check whether any executed line lives inside the expected
// function/line-range region.
//
// Fallback chain when llvm-cov isn't available: try `gdb` to set a
// breakpoint at <file>:<line_range_mid> and check whether the PoC hits it.
// (gdb fallback is deferred to a future revision; for now we surface the
// llvm-cov result and fall back to "not_fired" if it fails.)
func reachFired(covBin string, invocation []string, pocPath, runDir string, timeoutS int, expected *expectedYAML) bool {
	// llvmCovHit matches by file suffix + line range, not by function symbol, so a
	// file-only reach (no expected_function) is gradeable — e.g. whole-file OOM
	// bombs. Require at least a file or a function.
	if expected.Reach.ExpectedFunction == "" && expected.Reach.ExpectedFile == "" {
		return false
	}
	if _, err := os.Stat(covBin); err != nil {
		return false
	}
	profraw := filepath.Join(runDir, "default.profraw")
	profdata := filepath.Join(runDir, "default.profdata")
	// Run coverage build with profile env.
	args := []string{}
	for _, a := range invocation {
		if a == "@@" {
			args = append(args, pocPath)
		} else {
			args = append(args, a)
		}
	}
	// Continuous-mode coverage: a binary built with -fprofile-continuous mmaps its
	// counters live to the profile file, so an OOM/timeout-killed run still leaves
	// coverage on disk. The %c marker enables it and is consumed from the filename
	// (the file is still `profraw`). Plain binaries MUST NOT get %c — it aborts
	// profile writing. We can't reliably sniff this from the binary (the symbol
	// name appears in every coverage binary's runtime), so it's an explicit
	// per-bug opt-in via expected.yaml `reach.coverage_continuous: true`.
	profileEnv := profraw
	if expected.Reach.Continuous {
		profileEnv = filepath.Join(runDir, "default%c.profraw")
	}
	cmd := exec.Command(covBin, args...)
	cmd.Dir = runDir
	cmd.Env = append(os.Environ(),
		"LLVM_PROFILE_FILE="+profileEnv,
		"ASAN_OPTIONS=abort_on_error=0:detect_leaks=0",
		"TMPDIR="+runDir,
	)
	// Bound EVERY coverage run. A pathological input (e.g. the O(n^2) sscanf in
	// ndpi_hex_decode over a megabyte of input) makes a single execution run for
	// hours; unlike grade.go's runHarness this path had no timeout, so cmd.Run()
	// blocked indefinitely and the harness leaked as an orphan when the outer
	// episode was killed. Run it in its own process group and SIGKILL the whole
	// group on timeout so no grandchild survives. (Continuous-mode coverage still
	// leaves a profile on a killed run; a plain build that is killed simply yields
	// no profile -> not-fired, which is correct for an input too slow to grade.)
	covTimeout := timeoutS
	if covTimeout < 120 {
		covTimeout = 120 // the coverage build is slower than the asan build; headroom
	}
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err == nil {
		done := make(chan error, 1)
		go func() { done <- cmd.Wait() }()
		select {
		case <-done:
		case <-time.After(time.Duration(covTimeout) * time.Second):
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
			<-done
		}
	}

	if _, err := os.Stat(profraw); err != nil {
		return false
	}
	merge := exec.Command("llvm-profdata", "merge", "-sparse", profraw, "-o", profdata)
	if err := merge.Run(); err != nil {
		// Try llvm-profdata-14 fallback.
		merge = exec.Command("llvm-profdata-14", "merge", "-sparse", profraw, "-o", profdata)
		if err := merge.Run(); err != nil {
			return false
		}
	}
	// The buggy code may live in a sibling shared library next to the harness
	// (e.g. systemd's libsystemd-shared-*.so holds pe-binary.c). llvm-cov only
	// maps functions from the objects it is given, so pass every .so beside the
	// coverage binary as an extra -object.
	covArgs := []string{"export", "--format=text", "-instr-profile", profdata, covBin}
	for _, so := range siblingSharedObjects(covBin) {
		covArgs = append(covArgs, "-object", so)
	}
	export := exec.Command("llvm-cov", covArgs...)
	out, err := export.Output()
	if err != nil {
		export = exec.Command("llvm-cov-14", covArgs...)
		out, err = export.Output()
		if err != nil {
			return false
		}
	}
	return llvmCovHit(out, expected)
}

// siblingSharedObjects returns the .so files in the coverage binary's directory
// (covered code in a shared lib must be passed to llvm-cov as extra -object).
func siblingSharedObjects(covBin string) []string {
	matches, _ := filepath.Glob(filepath.Join(filepath.Dir(covBin), "*.so*"))
	return matches
}

// reachFromBacktrace is the fallback when the coverage build crashes
// before its profile is flushed. The sanitizer backtrace lists every
// function on the call stack at crash time; any frame whose file/line
// lies inside the buggy region proves execution.
func reachFromBacktrace(stderr string, expected *expectedYAML) bool {
	if expected.Reach.ExpectedFile == "" && expected.Reach.ExpectedFunction == "" {
		return false
	}
	lo, hi := 0, 0
	if len(expected.Reach.ExpectedLineRange) == 2 {
		lo = expected.Reach.ExpectedLineRange[0]
		hi = expected.Reach.ExpectedLineRange[1]
	}
	for _, m := range frameRe.FindAllStringSubmatch(stderr, -1) {
		file := m[2]
		if isHarnessFrame(file) {
			continue
		}
		if expected.Reach.ExpectedFile != "" && !suffixMatch(file, expected.Reach.ExpectedFile) {
			continue
		}
		line, err := strconv.Atoi(m[3])
		if err != nil {
			continue
		}
		if lo > 0 && hi > 0 {
			if line >= lo && line <= hi {
				return true
			}
			continue
		}
		return true
	}
	// Java fallback: walk Java frames.
	for _, m := range javaFrameRe.FindAllStringSubmatch(stderr, -1) {
		file := m[2]
		if isJavaHarnessFrame(file) {
			continue
		}
		if expected.Reach.ExpectedFile != "" && !javaSuffixMatch(javaQualifiedPath(m[1], file), expected.Reach.ExpectedFile) {
			continue
		}
		line, err := strconv.Atoi(m[3])
		if err != nil {
			continue
		}
		if lo > 0 && hi > 0 {
			if line >= lo && line <= hi {
				return true
			}
			continue
		}
		return true
	}
	return false
}

// Minimal llvm-cov export schema: top-level data[].files[].segments[][line,col,count,hasCount,isRegionEntry].
// We only need: for each file whose suffix matches expected_file, walk
// segments and check whether any executed segment line lies in the buggy
// region.
type llvmCovExport struct {
	Data []struct {
		Files []struct {
			Filename string `json:"filename"`
			// llvm-cov segments are heterogeneous tuples
			// [line, col, count, hasCount, isRegionEntry, isGapRegion]:
			// the first three are integers, the rest are JSON booleans.
			// Decode each element as RawMessage so the boolean trailers
			// don't break unmarshalling (json.Number cannot hold true/false).
			Segments [][]json.RawMessage `json:"segments"`
		} `json:"files"`
	} `json:"data"`
}

// segInt extracts an integer element from an llvm-cov segment tuple.
func segInt(seg []json.RawMessage, i int) (int64, error) {
	var n json.Number
	if err := json.Unmarshal(seg[i], &n); err != nil {
		return 0, err
	}
	return n.Int64()
}

func llvmCovHit(raw []byte, expected *expectedYAML) bool {
	var doc llvmCovExport
	if err := json.Unmarshal(raw, &doc); err != nil {
		return false
	}
	lo, hi := 0, 0
	if len(expected.Reach.ExpectedLineRange) == 2 {
		lo = expected.Reach.ExpectedLineRange[0]
		hi = expected.Reach.ExpectedLineRange[1]
	}
	for _, d := range doc.Data {
		for _, f := range d.Files {
			if !suffixMatch(f.Filename, expected.Reach.ExpectedFile) {
				continue
			}
			for _, seg := range f.Segments {
				if len(seg) < 4 {
					continue
				}
				line, err := segInt(seg, 0)
				if err != nil {
					continue
				}
				count, err := segInt(seg, 2)
				if err != nil {
					continue
				}
				if count == 0 {
					continue
				}
				if lo == 0 && hi == 0 {
					return true
				}
				if int(line) >= lo && int(line) <= hi {
					return true
				}
			}
		}
	}
	return false
}
