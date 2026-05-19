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
	path := filepath.Join(s.bugDir, "bench.yaml")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read bench.yaml: %w", err)
	}
	var b benchYAML
	if err := yaml.Unmarshal(data, &b); err != nil {
		return nil, fmt.Errorf("parse bench.yaml: %w", err)
	}
	return &b, nil
}

func (s *server) toolSetup(_ []byte) (any, error) {
	bench, err := s.loadBench()
	if err != nil {
		return nil, err
	}
	descPath := filepath.Join(s.bugDir, "description.txt")
	desc, err := os.ReadFile(descPath)
	if err != nil {
		return nil, fmt.Errorf("read description.txt: %w", err)
	}
	return map[string]any{
		"bug_id":   bench.BugID,
		"bug_desc": string(desc),
		"harness": map[string]any{
			"type":       bench.Harness.Type,
			"entrypoint": bench.Harness.Entrypoint,
			"invocation": bench.Harness.Invocation,
		},
		"build_configs":  []string{"debug", "debug-asan", "release-asan", "coverage"},
		"workspace_path": s.workspace,
		"bug_dir":        s.bugDir,
		"capability_set": bench.CapabilitySet,
		"notes":          bench.Notes,
	}, nil
}
