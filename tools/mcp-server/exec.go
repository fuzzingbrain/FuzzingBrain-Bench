package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"time"
)

const execTruncate = 2000

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

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "/bin/bash", "-c", p.Cmd)
	cmd.Dir = s.bugDir
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
