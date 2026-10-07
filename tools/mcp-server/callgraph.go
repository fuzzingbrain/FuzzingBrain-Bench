// The static call graph: the counterpart of gdb in the agent image.
//
// /challenge/callgraph.sqlite is built on the host by tools/callgraph/
// build_sqlite.py from the Joern graph of the SAME build the harness binary came
// from. Its schema (meta / functions / calls, see that script) is the contract:
// swap the graph builder, keep the schema, and nothing here changes.
//
// Three fixed tools (get_callers, get_callees, call_path) cover what an agent
// asks nine times in ten; query_graph takes read-only SQL for the tenth. The
// same four are reachable from the agent's shell as `cg ...`, because an agent
// that has gdb in its shell reaches for the shell -- see cgMain.
//
// The file is opened read-only and immutable (it never changes inside an
// image), so SQLite creates no journal next to it on the read-only root.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

const (
	callgraphDefaultPath = "/challenge/callgraph.sqlite"
	callgraphPathEnv     = "BENCH_CALLGRAPH"    // override the file (tests)
	callgraphDisableEnv  = "BENCH_NO_CALLGRAPH" // "1": the tools are not advertised (ablation)

	cgDefaultLimit = 50
	cgMaxLimit     = 500
	cgSQLTimeout   = 5 * time.Second
	cgSQLMaxRows   = 1000
	cgSQLDefRows   = 200
)

// CallgraphToolNames is the order they are advertised in. The Python side
// (fbbench.sweep.mcp_episode.CALLGRAPH_TOOL_NAMES) mirrors this list and the
// parity test checks the two agree.
var CallgraphToolNames = []string{"get_callers", "get_callees", "call_path", "query_graph"}

func callgraphPath() string {
	if p := os.Getenv(callgraphPathEnv); p != "" {
		return p
	}
	return callgraphDefaultPath
}

// callgraphAvailable: the file is readable and the ablation switch is off. This
// decides tools/list, so an agent is never offered a tool that cannot answer.
func callgraphAvailable() bool {
	if os.Getenv(callgraphDisableEnv) == "1" {
		return false
	}
	f, err := os.Open(callgraphPath())
	if err != nil {
		return false
	}
	f.Close()
	return true
}

type callgraph struct {
	db      *sql.DB
	entryID int64
	meta    map[string]string
}

var (
	cgOnce sync.Once
	cgInst *callgraph
	cgErr  error
)

// openCallgraph opens the file once per process (the server lives for the
// whole episode) and reads meta, including the entry's id.
func openCallgraph() (*callgraph, error) {
	cgOnce.Do(func() {
		path := callgraphPath()
		if _, err := os.Stat(path); err != nil {
			cgErr = fmt.Errorf("no call graph in this image (%s)", path)
			return
		}
		dsn := fmt.Sprintf("file:%s?mode=ro&immutable=1", path)
		db, err := sql.Open("sqlite", dsn)
		if err != nil {
			cgErr = err
			return
		}
		db.SetMaxOpenConns(2)
		cg := &callgraph{db: db, entryID: -1, meta: map[string]string{}}
		rows, err := db.Query("SELECT key, value FROM meta")
		if err != nil {
			cgErr = fmt.Errorf("callgraph meta: %w", err)
			return
		}
		for rows.Next() {
			var k, v string
			if rows.Scan(&k, &v) == nil {
				cg.meta[k] = v
			}
		}
		rows.Close()
		if id := cg.meta["entry_id"]; id != "" {
			fmt.Sscan(id, &cg.entryID)
		}
		cgInst = cg
	})
	return cgInst, cgErr
}

// fn is one row of `functions` as the agent sees it.
type fn struct {
	ID      int64  `json:"id"`
	Name    string `json:"name"`
	File    string `json:"file"`
	Line    int64  `json:"line"`
	LineEnd int64  `json:"line_end"`
	Depth   int64  `json:"depth"` // -1: not reachable from the harness entry in this graph
}

const fnCols = "id, name, file, line, line_end, depth"

func scanFns(rows *sql.Rows) ([]fn, error) {
	var out []fn
	for rows.Next() {
		var f fn
		if err := rows.Scan(&f.ID, &f.Name, &f.File, &f.Line, &f.LineEnd, &f.Depth); err != nil {
			return nil, err
		}
		out = append(out, f)
	}
	return out, rows.Err()
}

// resolve turns (name, file) into functions. `name` may also be a uid
// (name@file:line) or a numeric id from an earlier answer. `file` is matched as
// a path suffix, so "string.c" and "cups/string.c" both work.
func (cg *callgraph) resolve(ctx context.Context, name, file string) ([]fn, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return nil, errors.New("name is required")
	}
	var id int64
	if _, err := fmt.Sscanf(name, "%d", &id); err == nil && fmt.Sprint(id) == name {
		rows, err := cg.db.QueryContext(ctx, "SELECT "+fnCols+" FROM functions WHERE id = ?", id)
		if err != nil {
			return nil, err
		}
		defer rows.Close()
		return scanFns(rows)
	}
	if strings.Contains(name, "@") {
		rows, err := cg.db.QueryContext(ctx, "SELECT "+fnCols+" FROM functions WHERE uid = ?", name)
		if err != nil {
			return nil, err
		}
		defer rows.Close()
		return scanFns(rows)
	}
	q := "SELECT " + fnCols + " FROM functions WHERE name = ?"
	args := []any{name}
	if file = strings.TrimSpace(file); file != "" {
		q += " AND (file = ? OR file LIKE ?)"
		args = append(args, file, "%/"+strings.TrimPrefix(file, "/"))
	}
	q += " ORDER BY depth >= 0 DESC, depth, file, line LIMIT 50"
	rows, err := cg.db.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanFns(rows)
}

// similar: names that contain `name`, for a miss. Cheap enough on the largest
// graph (a 6 ms scan of 142k rows) and it saves the agent a guessing turn.
func (cg *callgraph) similar(ctx context.Context, name string) []string {
	rows, err := cg.db.QueryContext(ctx,
		"SELECT DISTINCT name FROM functions WHERE name LIKE ? ORDER BY length(name), name LIMIT 10",
		"%"+name+"%")
	if err != nil {
		return nil
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var s string
		if rows.Scan(&s) == nil {
			out = append(out, s)
		}
	}
	return out
}

func (cg *callgraph) graphNote() string {
	return fmt.Sprintf("static call graph of this build (%s functions, %s calls; %s reachable from %s)",
		cg.meta["n_functions"], cg.meta["n_calls"], cg.meta["reachable_from_entry"], cg.meta["entry"])
}

type cgLookupParams struct {
	Name  string `json:"name"`
	File  string `json:"file,omitempty"`
	Limit int    `json:"limit,omitempty"`
}

func clampLimit(n, def, max int) int {
	if n <= 0 {
		return def
	}
	if n > max {
		return max
	}
	return n
}

// target resolves the function a lookup is about, or returns the structured
// miss/ambiguity reply the tool should hand back instead.
func (cg *callgraph) target(ctx context.Context, name, file string) (*fn, map[string]any, error) {
	cands, err := cg.resolve(ctx, name, file)
	if err != nil {
		return nil, nil, err
	}
	switch {
	case len(cands) == 0:
		r := map[string]any{"error": fmt.Sprintf("no function named %q in the call graph", name)}
		if file != "" {
			r["error"] = fmt.Sprintf("no function named %q in file %q in the call graph", name, file)
		}
		if sim := cg.similar(ctx, name); len(sim) > 0 {
			r["similar_names"] = sim
		}
		return nil, r, nil
	case len(cands) > 1:
		return nil, map[string]any{
			"ambiguous":  true,
			"message":    fmt.Sprintf("%d functions are named %q; call again with `file` set to one of these", len(cands), name),
			"candidates": cands,
		}, nil
	}
	return &cands[0], nil, nil
}

// neighbors is get_callers (dir="callers") and get_callees (dir="callees").
func (cg *callgraph) neighbors(ctx context.Context, p cgLookupParams, dir string) (any, error) {
	t, miss, err := cg.target(ctx, p.Name, p.File)
	if err != nil || miss != nil {
		return miss, err
	}
	limit := clampLimit(p.Limit, cgDefaultLimit, cgMaxLimit)
	from, to := "caller", "callee" // callers of t: rows where callee = t, return caller
	if dir == "callees" {
		from, to = "callee", "caller"
	}
	var total int64
	if err := cg.db.QueryRowContext(ctx,
		fmt.Sprintf("SELECT count(*) FROM calls WHERE %s = ?", to), t.ID).Scan(&total); err != nil {
		return nil, err
	}
	rows, err := cg.db.QueryContext(ctx, fmt.Sprintf(
		"SELECT f.id, f.name, f.file, f.line, f.line_end, f.depth FROM calls c "+
			"JOIN functions f ON f.id = c.%s WHERE c.%s = ? "+
			"ORDER BY f.depth >= 0 DESC, f.depth, f.file, f.line LIMIT ?", from, to), t.ID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	list, err := scanFns(rows)
	if err != nil {
		return nil, err
	}
	if list == nil {
		list = []fn{}
	}
	return map[string]any{
		"function":  t,
		dir:         list,
		"total":     total,
		"truncated": int64(len(list)) < total,
		"graph":     cg.graphNote(),
	}, nil
}

// path walks `parent` from the function back to the harness entry.
func (cg *callgraph) path(ctx context.Context, p cgLookupParams) (any, error) {
	t, miss, err := cg.target(ctx, p.Name, p.File)
	if err != nil || miss != nil {
		return miss, err
	}
	if t.Depth < 0 {
		return map[string]any{
			"function":  t,
			"reachable": false,
			"message": "not reachable from the harness entry in this static graph. That is not proof " +
				"it is unreachable: calls through function pointers, virtual dispatch and some " +
				"files are missing from the graph. get_callers() still works on it.",
			"graph": cg.graphNote(),
		}, nil
	}
	chain := []fn{*t}
	cur := t.ID
	for i := int64(0); i <= t.Depth && cur != cg.entryID; i++ {
		var parent sql.NullInt64
		var f fn
		err := cg.db.QueryRowContext(ctx,
			"SELECT "+fnCols+", parent FROM functions WHERE id = ?", cur).
			Scan(&f.ID, &f.Name, &f.File, &f.Line, &f.LineEnd, &f.Depth, &parent)
		if err != nil || !parent.Valid {
			break
		}
		cur = parent.Int64
		var pf fn
		if err := cg.db.QueryRowContext(ctx, "SELECT "+fnCols+" FROM functions WHERE id = ?", cur).
			Scan(&pf.ID, &pf.Name, &pf.File, &pf.Line, &pf.LineEnd, &pf.Depth); err != nil {
			break
		}
		chain = append(chain, pf)
	}
	// entry first
	for i, j := 0, len(chain)-1; i < j; i, j = i+1, j-1 {
		chain[i], chain[j] = chain[j], chain[i]
	}
	return map[string]any{
		"function":  t,
		"reachable": true,
		"depth":     t.Depth,
		"path":      chain,
		"note":      "one shortest path in the static graph; other call chains may exist",
		"graph":     cg.graphNote(),
	}, nil
}

type cgQueryParams struct {
	SQL   string `json:"sql"`
	Limit int    `json:"limit,omitempty"`
}

var cgForbidden = regexp.MustCompile(`(?i)\b(attach|detach|pragma|insert|update|delete|drop|alter|create|replace|vacuum|reindex|begin|commit|rollback|savepoint|release)\b`)

// query runs one read-only SELECT with a timeout and a row cap. The connection
// is already read-only and immutable; the keyword screen is so the error the
// agent gets names the rule rather than SQLite's internals.
func (cg *callgraph) query(ctx context.Context, p cgQueryParams) (any, error) {
	q := strings.TrimSpace(strings.TrimSuffix(strings.TrimSpace(p.SQL), ";"))
	if q == "" {
		return nil, errors.New("sql is required")
	}
	if strings.Contains(q, ";") {
		return nil, errors.New("one statement per call")
	}
	head := strings.ToLower(q)
	if !(strings.HasPrefix(head, "select") || strings.HasPrefix(head, "with") || strings.HasPrefix(head, "explain")) {
		return nil, errors.New("read-only: the statement must start with SELECT or WITH")
	}
	if m := cgForbidden.FindString(q); m != "" {
		return nil, fmt.Errorf("read-only: %q is not allowed", m)
	}
	limit := clampLimit(p.Limit, cgSQLDefRows, cgSQLMaxRows)
	ctx, cancel := context.WithTimeout(ctx, cgSQLTimeout)
	defer cancel()
	t0 := time.Now()
	rows, err := cg.db.QueryContext(ctx, q)
	if err != nil {
		return nil, fmt.Errorf("sql: %v", err)
	}
	defer rows.Close()
	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	var out [][]any
	truncated := false
	for rows.Next() {
		if len(out) >= limit {
			truncated = true
			break
		}
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, err
		}
		for i, v := range vals {
			if b, ok := v.([]byte); ok {
				vals[i] = string(b)
			}
		}
		out = append(out, vals)
	}
	if err := rows.Err(); err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return nil, fmt.Errorf("sql: timed out after %s; narrow the query (functions.depth and the name/file indexes are cheap)", cgSQLTimeout)
		}
		return nil, fmt.Errorf("sql: %v", err)
	}
	if out == nil {
		out = [][]any{}
	}
	return map[string]any{
		"columns":     cols,
		"rows":        out,
		"row_count":   len(out),
		"truncated":   truncated,
		"duration_ms": time.Since(t0).Milliseconds(),
	}, nil
}

// ------------------------------------------------------------------ tools

func (s *server) toolCallgraph(name string, raw json.RawMessage) (any, error) {
	if !callgraphAvailable() {
		return nil, errors.New("no call graph is available in this image")
	}
	cg, err := openCallgraph()
	if err != nil {
		return nil, err
	}
	ctx := context.Background()
	switch name {
	case "get_callers", "get_callees":
		var p cgLookupParams
		if len(raw) > 0 {
			if err := json.Unmarshal(raw, &p); err != nil {
				return nil, fmt.Errorf("invalid params: %w", err)
			}
		}
		return cg.neighbors(ctx, p, strings.TrimPrefix(name, "get_"))
	case "call_path":
		var p cgLookupParams
		if len(raw) > 0 {
			if err := json.Unmarshal(raw, &p); err != nil {
				return nil, fmt.Errorf("invalid params: %w", err)
			}
		}
		return cg.path(ctx, p)
	case "query_graph":
		var p cgQueryParams
		if len(raw) > 0 {
			if err := json.Unmarshal(raw, &p); err != nil {
				return nil, fmt.Errorf("invalid params: %w", err)
			}
		}
		return cg.query(ctx, p)
	}
	return nil, fmt.Errorf("unknown call-graph tool %q", name)
}

func isCallgraphTool(name string) bool {
	for _, n := range CallgraphToolNames {
		if n == name {
			return true
		}
	}
	return false
}

const cgSchemaDoc = "Tables: functions(id, uid 'name@file:line', name, file, line, line_end, depth, parent) " +
	"and calls(caller, callee) where caller/callee are functions.id; meta(key, value). " +
	"depth is the BFS distance from the harness entry (-1 = not reachable in this graph), " +
	"parent the predecessor on one shortest path. Indexed: functions.name, functions.file, " +
	"calls.caller, calls.callee."

func callgraphToolSchemas() []map[string]any {
	lookup := func(desc string) map[string]any {
		return map[string]any{
			"type": "object",
			"properties": map[string]any{
				"name":  map[string]any{"type": "string", "description": "Function name (C/C++/Java method name without class), or a uid 'name@file:line' or numeric id from an earlier answer."},
				"file":  map[string]any{"type": "string", "description": "Optional: disambiguate same-named functions by file (path suffix, e.g. 'string.c' or 'cups/string.c')."},
				"limit": map[string]any{"type": "integer", "description": fmt.Sprintf("Max results (default %d, max %d).%s", cgDefaultLimit, cgMaxLimit, desc)},
			},
			"required": []string{"name"},
		}
	}
	common := " Each result is {id, name, file, line, line_end, depth}: read its source with exec `sed -n LINE,LINE_ENDp /challenge/src/FILE`. The graph is STATIC and from the harness build: calls through function pointers, virtual dispatch and some files are missing, so an empty answer is evidence, not proof."
	return []map[string]any{
		{
			"name":        "get_callers",
			"description": "Static call graph: the functions that call NAME, nearest to the harness entry first (total and truncated flag included). If several functions share the name you get the candidates back and pass `file`." + common,
			"inputSchema": lookup(""),
		},
		{
			"name":        "get_callees",
			"description": "Static call graph: the functions NAME calls, nearest to the harness entry first (total and truncated flag included). If several functions share the name you get the candidates back and pass `file`." + common,
			"inputSchema": lookup(""),
		},
		{
			"name":        "call_path",
			"description": "Static call graph: one shortest call chain from the harness entry (LLVMFuzzerTestOneInput / fuzzerTestOneInput) down to NAME, as a list of functions entry-first, with its depth. reachable:false means no path in this graph -- which can be a gap in the graph (indirect calls) rather than the truth." + common,
			"inputSchema": lookup(""),
		},
		{
			"name":        "query_graph",
			"description": "Static call graph: run one read-only SQL SELECT against it (SQLite) when the fixed tools do not fit -- e.g. every function in a file that the entry reaches, functions with many callers, k-hop neighbourhoods with a recursive CTE. " + cgSchemaDoc + " 5 s timeout, rows capped by `limit`. Example: SELECT name, file, line, depth FROM functions WHERE file LIKE '%parser%' AND depth >= 0 ORDER BY depth",
			"inputSchema": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"sql":   map[string]any{"type": "string", "description": "One SELECT (or WITH ... SELECT) statement."},
					"limit": map[string]any{"type": "integer", "description": fmt.Sprintf("Max rows (default %d, max %d).", cgSQLDefRows, cgSQLMaxRows)},
				},
				"required": []string{"sql"},
			},
		},
	}
}

// ---------------------------------------------------------------- cg CLI
//
// `cg` is this binary under another name (a wrapper script in the image), so the
// agent's shell has the same four questions without the MCP envelope:
//
//   cg callers NAME [FILE]      cg callees NAME [FILE]
//   cg path NAME [FILE]         cg sql "SELECT ..."        cg info
//
// Output is JSON (the tool result verbatim) -- pipes into jq-less shells still
// read it, and it is exactly what the MCP tool would have said.

func cgMain(args []string) int {
	usage := func() int {
		fmt.Fprintln(os.Stderr, "usage: cg callers|callees|path NAME [FILE]   |   cg sql \"SELECT ...\" [LIMIT]   |   cg info")
		return 2
	}
	if len(args) == 0 {
		return usage()
	}
	if !callgraphAvailable() {
		fmt.Fprintln(os.Stderr, "cg: no call graph is available in this image")
		return 1
	}
	cg, err := openCallgraph()
	if err != nil {
		fmt.Fprintln(os.Stderr, "cg:", err)
		return 1
	}
	ctx := context.Background()
	var res any
	switch args[0] {
	case "callers", "callees":
		if len(args) < 2 {
			return usage()
		}
		p := cgLookupParams{Name: args[1]}
		if len(args) > 2 {
			p.File = args[2]
		}
		res, err = cg.neighbors(ctx, p, args[0])
	case "path":
		if len(args) < 2 {
			return usage()
		}
		p := cgLookupParams{Name: args[1]}
		if len(args) > 2 {
			p.File = args[2]
		}
		res, err = cg.path(ctx, p)
	case "sql":
		if len(args) < 2 {
			return usage()
		}
		p := cgQueryParams{SQL: args[1]}
		if len(args) > 2 {
			fmt.Sscan(args[2], &p.Limit)
		}
		res, err = cg.query(ctx, p)
	case "info":
		res = map[string]any{"meta": cg.meta, "schema": cgSchemaDoc, "path": callgraphPath()}
	default:
		return usage()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "cg:", err)
		return 1
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", " ")
	enc.Encode(res)
	return 0
}

// invokedAsCG: the binary was started through its `cg` name or with `cg` as the
// first argument.
func invokedAsCG(args []string) ([]string, bool) {
	if filepath.Base(args[0]) == "cg" {
		return args[1:], true
	}
	if len(args) > 1 && args[1] == "cg" {
		return args[2:], true
	}
	return nil, false
}
