package main

// Sealed-challenge grading. Two halves live here:
//
//   gradeRemote(abs)  — CLIENT side. Called from toolGrade when BENCH_GRADE_URL
//                       is set. POSTs the candidate input bytes to the remote
//                       grading service and returns its JSON verdict verbatim.
//                       The challenge host holds NO answer key.
//
//   runGradeServer()  — ORACLE side. `mcp-server -grade-server :PORT
//                       -oracle-root DIR` serves POST /grade?bug=<id>: it writes
//                       the posted bytes into a fresh per-request workspace,
//                       points oracleDir at <oracle-root>/<bug>, and runs the
//                       SAME toolGrade locally (gradeURL empty there), returning
//                       the verdict. 100% of the grading logic is reused; the
//                       answer key never leaves this host.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

// ---- client side -------------------------------------------------------------

func (s *server) gradeRemote(abs string) (any, error) {
	data, err := os.ReadFile(abs)
	if err != nil {
		return nil, fmt.Errorf("read candidate: %w", err)
	}
	if s.bugID == "" {
		return nil, fmt.Errorf("BENCH_BUG_ID must be set for remote grading")
	}
	url := s.gradeURL + "/grade?bug=" + s.bugID
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/octet-stream")
	// When the oracle sits behind an ngrok free/dev domain, browser-like requests
	// get an HTML interstitial. This header tells ngrok to skip it so the verdict
	// JSON always comes back clean, regardless of how the request is classified.
	req.Header.Set("ngrok-skip-browser-warning", "true")
	cl := &http.Client{Timeout: 600 * time.Second}
	resp, err := cl.Do(req)
	if err != nil {
		return nil, fmt.Errorf("remote grade: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("remote grade status %d: %s", resp.StatusCode, string(trunc(string(body), 300)))
	}
	var out map[string]any
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("remote grade decode: %w", err)
	}
	// The oracle returns the full verdict (capabilities/agreed/evidence) so the
	// TRUSTED runner can score. But this proxy result is exactly what the AGENT's
	// grade() returns, so seal the verdict unless the runner explicitly asked to
	// reveal it (BENCH_GRADE_REVEAL=1). Codex / sealed images leave it unset and
	// see only harness_output — no leak of which rungs fired. (Mirrors toolGrade.)
	if os.Getenv("BENCH_GRADE_REVEAL") != "1" {
		sealed := map[string]any{}
		if ho, ok := out["harness_output"]; ok {
			sealed["harness_output"] = ho
		}
		if d, ok := out["duration_ms"]; ok {
			sealed["duration_ms"] = d
		}
		return sealed, nil
	}
	return out, nil
}

func trunc(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

// ---- oracle side -------------------------------------------------------------

func runGradeServer(addr, oracleRoot string) {
	// The oracle is trusted infra: its HTTP /grade response MUST carry the full
	// verdict (capabilities/evidence) so the in-container proxy / verify tooling
	// can score. Force reveal here so the local toolGrade it calls never seals
	// the verdict on the oracle side. Agent-facing sealing happens at the
	// in-container gradeRemote, which is the real gatekeeper. (No agent can reach
	// this oracle directly — it is network-isolated from the challenge sandbox.)
	os.Setenv("BENCH_GRADE_REVEAL", "1")
	mux := http.NewServeMux()
	mux.HandleFunc("/grade", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}
		bug := r.URL.Query().Get("bug")
		if bug == "" || filepath.Base(bug) != bug {
			http.Error(w, "bad bug id", http.StatusBadRequest)
			return
		}
		oracleDir := filepath.Join(oracleRoot, bug)
		if st, err := os.Stat(oracleDir); err != nil || !st.IsDir() {
			http.Error(w, "unknown bug", http.StatusNotFound)
			return
		}
		data, err := io.ReadAll(io.LimitReader(r.Body, 256<<20)) // 256 MiB cap
		if err != nil {
			http.Error(w, "read body", http.StatusBadRequest)
			return
		}
		ws, err := os.MkdirTemp("", "fbgrade-")
		if err != nil {
			http.Error(w, "workspace", http.StatusInternalServerError)
			return
		}
		defer os.RemoveAll(ws)
		inPath := filepath.Join(ws, "candidate.bin")
		if err := os.WriteFile(inPath, data, 0o600); err != nil {
			http.Error(w, "write candidate", http.StatusInternalServerError)
			return
		}
		// A local-grading server instance: gradeURL empty -> runs the real oracle.
		gs := &server{bugDir: oracleDir, workspace: ws, oracleDir: oracleDir}
		args, _ := json.Marshal(gradeParams{Path: inPath})
		res, err := gs.toolGrade(args)
		if err != nil {
			http.Error(w, "grade: "+err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(res)
	})
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("ok\n"))
	})
	log.Printf("grade server on %s, oracle root %s", addr, oracleRoot)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("grade server: %v", err)
	}
}
