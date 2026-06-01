package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"
)

const execTruncate = 2000

// execEnvDeny lists environment variables that must never reach the agent's
// shell: they would leak the oracle location or the privilege-separation
// config, defeating the point of running exec() unprivileged.
var execEnvDeny = map[string]bool{
	"BENCH_ORACLE_DIR": true,
	"BENCH_AGENT_UID":  true,
	"BENCH_AGENT_GID":  true,
}

// agentEnv returns the process environment with the oracle/privsep vars
// stripped. BENCH_BUG_DIR and BENCH_WORKSPACE are kept — the agent is meant
// to know those.
func agentEnv() []string {
	src := os.Environ()
	out := make([]string, 0, len(src))
	for _, kv := range src {
		k := kv
		if i := strings.IndexByte(kv, '='); i >= 0 {
			k = kv[:i]
		}
		if execEnvDeny[k] {
			continue
		}
		out = append(out, kv)
	}
	return out
}

type execParams struct {
	Cmd      string `json:"cmd"`
	TimeoutS int    `json:"timeout_s,omitempty"`
}

func (s *server) toolExec(args []byte) (any, error) {
	var p execParams
	if err := json.Unmarshal(args, &p); err != nil {
		return nil, fmt.Errorf("parse args: %w", err)
	}
	if p.Cmd == "" {
		return nil, fmt.Errorf("cmd required")
	}
	timeout := p.TimeoutS
	if timeout <= 0 {
		timeout = 60
	}

	// Refuse to run if we cannot guarantee no internet access (unless the
	// operator explicitly opted in). This closes the network cheat vector.
	if !s.netIsolate && !s.allowNet {
		return nil, fmt.Errorf("exec refused: network isolation unavailable on this host " +
			"(no user+net namespace). Set BENCH_ALLOW_NET=1 to allow networked exec.")
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	// When isolation is on, wrap the shell in a fresh user+network namespace
	// (`unshare -r -n`): the command sees only a down loopback, so it cannot
	// reach the network (DNS/TCP fail) — blocking upstream-issue/source/PoC
	// fetches. Falls through to a bare shell only under BENCH_ALLOW_NET=1.
	name, argv := "/bin/bash", []string{"-c", p.Cmd}
	if s.netIsolate {
		name = "unshare"
		argv = []string{"-r", "-n", "--", "/bin/bash", "-c", p.Cmd}
	}
	cmd := exec.CommandContext(ctx, name, argv...)
	cmd.Dir = s.bugDir
	cmd.Env = agentEnv()

	// Run the command in its own process group (Setpgid) so that on timeout we
	// can kill the *whole* tree, not just the bash parent. Without this, a
	// command like `find /` that bash backgrounds or that outlives bash gets
	// orphaned (reparented to init) and keeps the stdout/stderr pipe open,
	// wedging cmd.Run() forever waiting for pipe EOF.
	sysAttr := &syscall.SysProcAttr{Setpgid: true}
	if s.dropPrivs {
		sysAttr.Credential = &syscall.Credential{Uid: s.agentUID, Gid: s.agentGID}
	}
	cmd.SysProcAttr = sysAttr

	// On context cancellation/timeout, SIGKILL the entire process group
	// (negative PID targets the group) instead of just the bash leader.
	cmd.Cancel = func() error {
		return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	}
	// Backstop: if a descendant keeps the pipe open after the group is killed
	// — e.g. a process stuck in uninterruptible D-state that SIGKILL can't
	// reap — don't block Run() indefinitely. After WaitDelay, the pipes are
	// force-closed and Run() returns.
	cmd.WaitDelay = 5 * time.Second

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	start := time.Now()
	runErr := cmd.Run()
	duration := time.Since(start).Milliseconds()

	out, outTrunc := truncate(stdout.String(), execTruncate)
	errStr, errTrunc := truncate(stderr.String(), execTruncate)

	exitCode := 0
	if runErr != nil {
		if ee, ok := runErr.(*exec.ExitError); ok {
			exitCode = ee.ExitCode()
		} else if ctx.Err() == context.DeadlineExceeded {
			exitCode = 124
		} else {
			exitCode = -1
			errStr = errStr + "\n[exec error: " + runErr.Error() + "]"
		}
	}

	return map[string]any{
		"stdout":      out,
		"stderr":      errStr,
		"exit_code":   exitCode,
		"duration_ms": duration,
		"truncated": map[string]bool{
			"stdout": outTrunc,
			"stderr": errTrunc,
		},
	}, nil
}

func truncate(s string, n int) (string, bool) {
	if len(s) <= n {
		return s, false
	}
	return s[:n], true
}
