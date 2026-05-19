// FuzzingBrain Bench MCP server.
//
// Speaks line-delimited JSON-RPC 2.0 on stdin/stdout per the MCP transport
// convention. Implements the 6-tool contract from SPEC §4.
//
// Environment:
//   BENCH_BUG_DIR    absolute path to bugs/<project>/<bug_id>/
//   BENCH_WORKSPACE  absolute path to the runner's per-episode tmpdir
//
// Diagnostics go to stderr; nothing else.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"os"
)

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
	workspace string
	enc       *json.Encoder
}

func main() {
	log.SetPrefix("mcp-server: ")
	log.SetOutput(os.Stderr)

	bugDir := os.Getenv("BENCH_BUG_DIR")
	workspace := os.Getenv("BENCH_WORKSPACE")
	if bugDir == "" || workspace == "" {
		log.Fatal("BENCH_BUG_DIR and BENCH_WORKSPACE must be set")
	}

	if err := os.MkdirAll(workspace, 0o755); err != nil {
		log.Fatalf("workspace: %v", err)
	}

	srv := &server{
		bugDir:    bugDir,
		workspace: workspace,
		enc:       json.NewEncoder(os.Stdout),
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
				"name":    "fuzzingbrain-bench",
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
	case "grade":
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
			"name":        "setup",
			"description": "Return bug metadata and workspace pointers.",
			"inputSchema": map[string]any{"type": "object", "properties": map[string]any{}},
		},
		{
			"name":        "exec",
			"description": "Run a shell command via /bin/bash -c. cwd = BENCH_BUG_DIR.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"cmd":       map[string]any{"type": "string"},
					"timeout_s": map[string]any{"type": "integer"},
				},
				"required": []string{"cmd"},
			},
		},
		{
			"name":        "list_directory",
			"description": "List directory entries.",
			"inputSchema": map[string]any{
				"type":       "object",
				"properties": map[string]any{"path": map[string]any{"type": "string"}},
				"required":   []string{"path"},
			},
		},
		{
			"name":        "read_file",
			"description": "Read a file. Denied for oracle answer keys; see SPEC §4.4.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"path":   map[string]any{"type": "string"},
					"offset": map[string]any{"type": "integer"},
					"limit":  map[string]any{"type": "integer"},
				},
				"required": []string{"path"},
			},
		},
		{
			"name":        "write_file",
			"description": "Write a file under BENCH_WORKSPACE.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"path":    map[string]any{"type": "string"},
					"content": map[string]any{"type": "string"},
				},
				"required": []string{"path", "content"},
			},
		},
		{
			"name":        "grade",
			"description": "Grade a candidate PoC. Returns capability bitmap.",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"path": map[string]any{"type": "string"},
					"options": map[string]any{
						"type": "object",
						"properties": map[string]any{
							"round_count": map[string]any{"type": "integer"},
						},
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
