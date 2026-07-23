package main

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

type benchYAML struct {
	BugID          string `yaml:"bug_id"`
	Project        string `yaml:"project"`
	Title          string `yaml:"title"`
	UpstreamReport string `yaml:"upstream_report"`
	Target         struct {
		Repo        string `yaml:"repo"`
		VulnCommit  string `yaml:"vuln_commit"`
		Language    string `yaml:"language"`
		BuildSystem string `yaml:"build_system"`
	} `yaml:"target"`
	Harness struct {
		Type       string   `yaml:"type"`
		Entrypoint string   `yaml:"entrypoint"`
		Invocation []string `yaml:"invocation"`
		RSSLimitMB int      `yaml:"rss_limit_mb"`
		TimeoutS   int      `yaml:"timeout_s"`
		Provenance string   `yaml:"provenance"`
	} `yaml:"harness"`
	CapabilitySet []string `yaml:"capability_set"`
	Reproducibility struct {
		BaseImageDigest    string `yaml:"base_image_digest"`
		SnapshotDebianDate string `yaml:"snapshot_debian_date"`
		SourceDateEpoch    int64  `yaml:"source_date_epoch"`
	} `yaml:"reproducibility"`
	Status    string `yaml:"status"`
	CVE       string `yaml:"cve"`
	Disclosed string `yaml:"disclosed"`
	Notes     string `yaml:"notes"`
}

func (s *server) loadBench() (*benchYAML, error) {
	// The blind (full-scan) challenge ships a slim manifest named target.yaml;
	// the internal/oracle bundles keep the richer bench.yaml. Prefer target.yaml
	// so the agent-facing view never depends on a file literally named "bench".
	// metaDir holds the manifest in the sealed challenge; grade-server mode never
	// sets it, so fall back to bugDir (which there == the oracle bundle carrying
	// bench.yaml). Without this fallback every grade fails to load the manifest.
	dir := s.metaDir
	if dir == "" {
		dir = s.bugDir
	}
	var data []byte
	var err error
	for _, name := range []string{"target.yaml", "bench.yaml"} {
		data, err = os.ReadFile(filepath.Join(dir, name))
		if err == nil {
			break
		}
	}
	if err != nil {
		return nil, fmt.Errorf("read target manifest: %w", err)
	}
	var b benchYAML
	if err := yaml.Unmarshal(data, &b); err != nil {
		return nil, fmt.Errorf("parse target manifest: %w", err)
	}
	return &b, nil
}

func (s *server) toolSetup(_ []byte) (any, error) {
	bench, err := s.loadBench()
	if err != nil {
		return nil, err
	}
	out := map[string]any{
		// No "task"/description field: the task is conveyed entirely by the
		// system prompt, so setup() ships none (this also removes the old
		// description.txt fallback, which leaked a benchmark framing). Neutral
		// naming throughout: "source_dir" (not "bug_dir"), no case alias — a real
		// audit target hands you source + a harness, not a catalogued bug.
		//
		// project + language are public build facts (the harness source reveals
		// the project anyway; the language is obvious).
		"project":  bench.Project,
		"language": bench.Target.Language,
		"harness": map[string]any{
			"type":       bench.Harness.Type,
			"entrypoint": bench.Harness.Entrypoint,
			"invocation": bench.Harness.Invocation,
		},
		"workspace_path": s.workspace,
		"source_dir":     s.bugDir,
	}
	// capability_set (the scoring ladder) and notes are internal grading metadata
	// — they must NOT surface in the blind (full-scan) view, where bench.yaml is
	// stripped so both are empty. Emit them only when populated (diff-scan/normal).
	if len(bench.CapabilitySet) > 0 {
		out["capability_set"] = bench.CapabilitySet
	}
	if bench.Notes != "" {
		out["notes"] = bench.Notes
	}
	// The sanitizer the build is judged under is part of the fuzzing setup — a
	// real auditor always knows it — so it is surfaced in EVERY mode (full-scan
	// included; full-scan's blindness is about not knowing what/where the bug is
	// or its class, not about hiding the build's instrumentation). The value
	// comes from grader/expected.yaml class.sanitizer; we copy ONLY that field,
	// never class.expected (the answer).
	if exp, eerr := s.loadExpected(); eerr == nil && exp.Class.Sanitizer != "" {
		out["sanitizer"] = exp.Class.Sanitizer
	}
	return out, nil
}
