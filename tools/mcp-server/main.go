// FuzzingBrain Bench MCP server.
//
// Speaks line-delimited JSON-RPC 2.0 on stdin/stdout per the MCP transport
// convention. Implements the 6-tool contract from SPEC §4.
//
// Environment:
//
//	BENCH_BUG_DIR    absolute path to the agent-facing bug dir (no oracle files)
//	BENCH_WORKSPACE  absolute path to the runner's per-episode tmpdir
//	BENCH_ORACLE_DIR absolute path the grader reads expected.yaml + binaries
//	                 from. Defaults to BENCH_BUG_DIR (so the no-AI fb-bench
//	                 CLI, which points BUG_DIR at the real bug dir, still works).
//	BENCH_AGENT_UID  numeric uid to run exec() as. When set and the server is
//	BENCH_AGENT_GID  root, exec subprocesses drop to this (uid,gid) so the
//	                 agent's shell cannot read root-owned oracle files even by
//	                 absolute path / `find /`. No-op when unset or not root.
//
// Diagnostics go to stderr; nothing else.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
)

// probeNetNS reports whether this host can create an unprivileged user+network
// namespace (`unshare -r -n`). When true, exec() runs each command inside one
// so it has no route to the internet.
func probeNetNS() bool {
	return exec.Command("unshare", "-r", "-n", "--", "true").Run() == nil
}

type rpcRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Result  interface{}     `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    any    `json:"data,omitempty"`
}

type server struct {
	bugDir    string
	metaDir   string
	workspace string
	oracleDir string
	// gradeURL: when set (BENCH_GRADE_URL), grade() does NOT touch a local oracle
	// — it POSTs the candidate input to a remote grading service and returns its
	// verdict. This is the sealed-challenge path: the challenge ships only source
	// + harness (no answers); the answer-bearing oracle lives behind gradeURL.
	// bugID (BENCH_BUG_ID) selects which oracle the remote grades against.
	gradeURL string
	bugID    string
	// agentUID/agentGID are >0 and dropPrivs true only when BENCH_AGENT_UID is
	// set and the server runs as root; exec() then drops to this credential.
	agentUID  uint32
	agentGID  uint32
	dropPrivs bool
	// netIsolate: run exec() inside a fresh user+network namespace so the
	// agent's shell has NO internet (only a down loopback). Probed at startup.
	// allowNet: explicit override to permit networked exec when isolation is
	// unavailable (BENCH_ALLOW_NET=1) — otherwise exec() is refused.
	netIsolate bool
	allowNet   bool
	enc        *json.Encoder
}

func main() {
	log.SetPrefix("mcp-server: ")
	log.SetOutput(os.Stderr)

	// Grade-server mode (sealed-challenge oracle side):
	//   mcp-server -grade-server :PORT -oracle-root DIR
	// Serves POST /grade?bug=<id> and never speaks the stdio MCP protocol.
	if len(os.Args) > 1 && os.Args[1] == "-grade-server" {
		addr := ":8080"
		oracleRoot := "."
		for i := 2; i < len(os.Args)-1; i++ {
			switch os.Args[i] {
			case "-addr":
				addr = os.Args[i+1]
			case "-oracle-root":
				oracleRoot = os.Args[i+1]
			}
		}
		// also allow `-grade-server :PORT` shorthand
		if len(os.Args) > 2 && os.Args[2] != "" && os.Args[2][0] == ':' {
			addr = os.Args[2]
		}
		// Resolve to absolute: grading execs the harness with the per-request
		// workspace as cwd, so a relative oracle-root would make the harness path
		// relative-to-workspace and fork/exec would fail with ENOENT.
		if abs, err := filepath.Abs(oracleRoot); err == nil {
			oracleRoot = abs
		}
		runGradeServer(addr, oracleRoot)
		return
	}

	bugDir := os.Getenv("BENCH_BUG_DIR")
	workspace := os.Getenv("BENCH_WORKSPACE")
	if bugDir == "" || workspace == "" {
		log.Fatal("BENCH_BUG_DIR and BENCH_WORKSPACE must be set")
	}
	oracleDir := os.Getenv("BENCH_ORACLE_DIR")
	if oracleDir == "" {
		oracleDir = bugDir
	}
	// metaDir holds the target manifest + task text. Kept OUT of the agent-facing
	// source dir (bugDir) in the sealed challenge, so `ls /src` shows only a plain
	// source checkout (harness/ + src/) with no benchmark-shaped manifest beside
	// it. Defaults to bugDir for the local/dev path where nothing is hidden.
	metaDir := os.Getenv("BENCH_META_DIR")
	if metaDir == "" {
		metaDir = bugDir
	}

	if err := os.MkdirAll(workspace, 0o755); err != nil {
		log.Fatalf("workspace: %v", err)
	}

	srv := &server{
		bugDir:    bugDir,
		metaDir:   metaDir,
		workspace: workspace,
		oracleDir: oracleDir,
		gradeURL:  os.Getenv("BENCH_GRADE_URL"),
		bugID:     os.Getenv("BENCH_BUG_ID"),
		enc:       json.NewEncoder(os.Stdout),
	}

	// Tier 2: privilege separation for exec(). Only engages when we are root
	// and an agent uid is configured — otherwise exec runs as the server uid
	// (unchanged behaviour, relying on Tier 1 sandbox staging by the runner).
	if uidStr := os.Getenv("BENCH_AGENT_UID"); uidStr != "" && os.Geteuid() == 0 {
		uid, err := strconv.Atoi(uidStr)
		if err != nil || uid <= 0 {
			log.Fatalf("BENCH_AGENT_UID must be a positive integer, got %q", uidStr)
		}
		gid := uid
		if g := os.Getenv("BENCH_AGENT_GID"); g != "" {
			if gv, err := strconv.Atoi(g); err == nil && gv > 0 {
				gid = gv
			}
		}
		srv.agentUID = uint32(uid)
		srv.agentGID = uint32(gid)
		srv.dropPrivs = true
		// The agent's exec/write_file land in workspace; make it owned by the
		// unprivileged uid so the shell can create and edit files there.
		if err := chownTree(workspace, uid, gid); err != nil {
			log.Printf("warn: chown workspace: %v", err)
		}
		log.Printf("privilege separation on: exec() runs as uid=%d gid=%d", uid, gid)
	}

	// Network isolation: prevent the agent's exec() from reaching the internet
	// (a cheat vector — fetching the upstream issue / source / reference PoC).
	srv.allowNet = os.Getenv("BENCH_ALLOW_NET") == "1"
	srv.netIsolate = probeNetNS()
	switch {
	case srv.netIsolate:
		log.Printf("network isolation ON: exec() runs in an isolated net namespace (no internet)")
	case srv.allowNet:
		log.Printf("WARNING: net-namespace isolation unavailable; BENCH_ALLOW_NET=1 set — exec() HAS internet access")
	default:
		log.Printf("network isolation UNAVAILABLE: exec() will be refused (set BENCH_ALLOW_NET=1 to override)")
	}

	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 0, 64*1024), 16*1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var req rpcRequest
		if err := json.Unmarshal(line, &req); err != nil {
			srv.writeError(nil, -32700, "parse error", err.Error())
			continue
		}
		srv.dispatch(&req)
	}
	if err := scanner.Err(); err != nil {
		log.Printf("stdin: %v", err)
	}
}

func (s *server) dispatch(req *rpcRequest) {
	switch req.Method {
	case "initialize":
		s.writeResult(req.ID, map[string]any{
			"protocolVersion": "2024-11-05",
			"capabilities":    map[string]any{"tools": map[string]any{}},
			"serverInfo": map[string]any{
				"name":    "harness-tools",
				"version": "0.1.0",
			},
		})
	case "notifications/initialized":
		// no response for notifications
	case "tools/list":
		s.writeResult(req.ID, map[string]any{"tools": toolSchemas()})
	case "tools/call":
		s.handleToolCall(req)
	default:
		s.writeError(req.ID, -32601, "method not found", req.Method)
	}
}

type toolCallParams struct {
	Name      string          `json:"name"`
	Arguments json.RawMessage `json:"arguments,omitempty"`
}

func (s *server) handleToolCall(req *rpcRequest) {
	var p toolCallParams
	if err := json.Unmarshal(req.Params, &p); err != nil {
		s.writeError(req.ID, -32602, "invalid params", err.Error())
		return
	}
	var (
		result any
		err    error
	)
	switch p.Name {
	case "setup":
		result, err = s.toolSetup(p.Arguments)
	case "exec":
		result, err = s.toolExec(p.Arguments)
	case "list_directory":
		result, err = s.toolListDirectory(p.Arguments)
	case "read_file":
		result, err = s.toolReadFile(p.Arguments)
	case "write_file":
		result, err = s.toolWriteFile(p.Arguments)
	case "run_input", "verify_poc", "grade": // verify_poc/grade kept as hidden aliases
		result, err = s.toolGrade(p.Arguments)
	default:
		s.writeError(req.ID, -32602, "unknown tool", p.Name)
		return
	}
	if err != nil {
		s.writeError(req.ID, -32000, "tool error", err.Error())
		return
	}
	payload, _ := json.Marshal(result)
	s.writeResult(req.ID, map[string]any{
		"content": []map[string]any{
			{"type": "text", "text": string(payload)},
		},
		"structuredContent": result,
	})
}

func (s *server) writeResult(id json.RawMessage, v any) {
	if id == nil {
		return
	}
	if err := s.enc.Encode(rpcResponse{JSONRPC: "2.0", ID: id, Result: v}); err != nil {
		log.Printf("encode result: %v", err)
	}
}

func (s *server) writeError(id json.RawMessage, code int, msg string, data any) {
	resp := rpcResponse{JSONRPC: "2.0", ID: id, Error: &rpcError{Code: code, Message: msg, Data: data}}
	if id == nil {
		resp.ID = json.RawMessage("null")
	}
	if err := s.enc.Encode(resp); err != nil {
		log.Printf("encode error: %v", err)
	}
}

func toolSchemas() []map[string]any {
	return []map[string]any{
		{
			"name": "setup",
			"description": "Return the task setup: the target project name and language, the fuzz " +
				"harness info (entrypoint and how it is invoked), the sanitizer the build is judged " +
				"under, and the workspace and source-directory paths. Takes no arguments. Call it " +
				"first — the other tools work off the paths it returns.",
			"inputSchema": map[string]any{"type": "object", "properties": map[string]any{}},
		},
		{
			"name": "exec",
			"description": "Run a shell command with /bin/bash -c inside the project's source " +
				"directory (that is the working directory). The sandbox is network-isolated — there " +
				"is no internet access. Use it to inspect the source and to build or compute candidate " +
				"input bytes. Returns the command's stdout and stderr (truncated if very long) and its " +
				"exit status.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"cmd": map[string]any{
						"type":        "string",
						"description": "The shell command to run, e.g. `grep -rn parse src/`.",
					},
					"timeout_s": map[string]any{
						"type":        "integer",
						"description": "Optional wall-clock timeout in seconds (default 60, maximum 300). The command is killed if it runs longer.",
					},
				},
				"required": []string{"cmd"},
			},
		},
		{
			"name": "list_directory",
			"description": "List the entries of a directory. A relative path is resolved against the " +
				"staged target root; the path must stay within the staged target tree (harness/, src/, " +
				"…) or the workspace.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"path": map[string]any{
						"type":        "string",
						"description": "Directory to list, absolute or relative to the staged target root (e.g. `src` or `harness`).",
					},
				},
				"required": []string{"path"},
			},
		},
		{
			"name": "read_file",
			"description": "Read a file's contents. A relative path is resolved against the staged " +
				"target root; the path must stay within the staged target tree (harness/, src/, …) or " +
				"the workspace. Some build artifacts are access-restricted and cannot be read.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"path": map[string]any{
						"type":        "string",
						"description": "File to read, absolute or relative to the staged target root (e.g. `harness/fuzz.cc`, `src/foo.c`).",
					},
					"offset": map[string]any{
						"type":        "integer",
						"description": "Optional byte offset to start reading from (default 0).",
					},
					"limit": map[string]any{
						"type":        "integer",
						"description": "Optional maximum number of bytes to read (default 65536).",
					},
				},
				"required": []string{"path"},
			},
		},
		{
			"name": "write_file",
			"description": "Write a file, creating parent directories as needed. The path must be " +
				"inside the workspace directory returned by setup(). Use it to save a candidate input " +
				"before running it through run_input().",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"path": map[string]any{
						"type":        "string",
						"description": "Destination path; must be inside the workspace directory (setup()'s workspace_path).",
					},
					"content": map[string]any{
						"type":        "string",
						"description": "The exact contents to write to the file.",
					},
				},
				"required": []string{"path", "content"},
			},
		},
		{
			"name": "run_input",
			"description": "Run one candidate input through the official sanitizer-instrumented target " +
				"harness — a single execution of the target on that input — and return its raw stdout, " +
				"stderr, exit code, and terminating signal, including any sanitizer or crash report. " +
				"This is your only ground-truth feedback: read the output to see whether the input " +
				"reached the target, whether it crashed, and where, then iterate.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"path": map[string]any{
						"type":        "string",
						"description": "Path to the candidate input file to run; must be inside the workspace directory (e.g. a file you just wrote with write_file).",
					},
				},
				"required": []string{"path"},
			},
		},
	}
}

func mustJSON(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Sprintf("%v", v)
	}
	return string(b)
}

// chownTree recursively chowns root to (uid,gid). Best-effort: it logs and
// continues past individual failures so a single odd entry can't abort startup.
func chownTree(root string, uid, gid int) error {
	return filepath.Walk(root, func(p string, _ os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		if err := os.Lchown(p, uid, gid); err != nil {
			log.Printf("warn: chown %s: %v", p, err)
		}
		return nil
	})
}
