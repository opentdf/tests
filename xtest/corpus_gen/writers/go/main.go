// Corpus writer for the Go SDK. Reads a JSON array of WriteJobs and writes one
// TDF per job. See corpus_gen/selfcheck.py for the job shape.
package main

import (
	"bytes"
	"context"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"

	"github.com/opentdf/platform/sdk"
)

const (
	sdkModule      = "github.com/opentdf/platform/sdk"
	minSegmentSize = 16 * 1024
	maxSegmentSize = 4 * 1024 * 1024
)

type kasSpec struct {
	URL string `json:"url"`
	KID string `json:"kid"`
	Alg string `json:"alg"`
}

type splitSpec struct {
	KAS *int   `json:"kas"` // nil when missing or null
	SID string `json:"sid"`
}

type statementSpec struct {
	Format string `json:"format"`
	Schema string `json:"schema"`
	Value  string `json:"value"`
}

type assertionSpec struct {
	Kind           string         `json:"kind"`
	Alg            string         `json:"alg"`
	KeyPEM         string         `json:"key_pem"`
	X5C            []string       `json:"x5c"`
	ID             *string        `json:"id"`
	Scope          *string        `json:"scope"`
	AppliesToState *string        `json:"applies_to_state"`
	Statement      *statementSpec `json:"statement"`
}

type job struct {
	Out               string          `json:"out"`
	Plaintext         string          `json:"plaintext"`
	KAS               []kasSpec       `json:"kas"`
	Split             []splitSpec     `json:"split"`
	Attributes        []string        `json:"attributes"`
	SegmentSize       *int64          `json:"segment_size"`
	MimeType          *string         `json:"mime_type"`
	EncryptedMetadata *string         `json:"encrypted_metadata"`
	Assertions        []assertionSpec `json:"assertions"`
	TargetMode        *string         `json:"target_mode"`
}

func sdkVersion() string {
	if bi, ok := debug.ReadBuildInfo(); ok {
		for _, d := range bi.Deps {
			if d.Path == sdkModule {
				return d.Version
			}
		}
	}
	return "unknown"
}

// handlingShape applies the optional id, scope, applies_to_state and statement.
func handlingShape(a assertionSpec, cfg *sdk.AssertionConfig) error {
	if a.ID != nil {
		if *a.ID == "" {
			return errors.New("assertion id must not be empty")
		}
		cfg.ID = *a.ID
	}
	if a.Scope != nil {
		switch *a.Scope {
		case "tdo":
			cfg.Scope = sdk.TrustedDataObjScope
		case "payload":
			cfg.Scope = sdk.PayloadScope
		default:
			return fmt.Errorf("scope %q not one of tdo, payload", *a.Scope)
		}
	}
	if a.AppliesToState != nil {
		switch *a.AppliesToState {
		case "encrypted":
			cfg.AppliesToState = sdk.Encrypted
		case "unencrypted":
			cfg.AppliesToState = sdk.Unencrypted
		default:
			return fmt.Errorf("applies_to_state %q not one of encrypted, unencrypted", *a.AppliesToState)
		}
	}
	if s := a.Statement; s != nil {
		if s.Format == "" || s.Schema == "" || s.Value == "" {
			return errors.New("statement needs non-empty format, schema and value")
		}
		cfg.Statement = sdk.Statement{Format: s.Format, Schema: s.Schema, Value: s.Value}
	}
	return nil
}

// assertionConfig returns nil for system-metadata, which has its own option.
func assertionConfig(a assertionSpec) (*sdk.AssertionConfig, error) {
	switch a.Kind {
	case "system-metadata":
		if a.ID != nil || a.Scope != nil || a.AppliesToState != nil || a.Statement != nil {
			return nil, errors.New("system-metadata takes no id, scope, applies_to_state or statement; the SDK builds it")
		}
		return nil, nil
	case "handling":
		if len(a.X5C) > 0 {
			return nil, errors.New("x5c assertions are not supported by the Go writer")
		}
		cfg := sdk.AssertionConfig{
			ID:             "handling-" + strings.ToLower(a.Alg),
			Type:           sdk.HandlingAssertion,
			Scope:          sdk.TrustedDataObjScope,
			AppliesToState: sdk.Encrypted,
			Statement: sdk.Statement{
				Format: "json",
				Schema: "urn:corpus:handling",
				Value:  `{"handling":"corpus"}`,
			},
		}
		if err := handlingShape(a, &cfg); err != nil {
			return nil, err
		}
		switch a.Alg {
		case "HS256":
			cfg.SigningKey = sdk.AssertionKey{Alg: sdk.AssertionKeyAlgHS256, Key: []byte(a.KeyPEM)}
		case "RS256":
			key, err := parseRSAKey(a.KeyPEM)
			if err != nil {
				return nil, err
			}
			cfg.SigningKey = sdk.AssertionKey{Alg: sdk.AssertionKeyAlgRS256, Key: key}
		default:
			return nil, fmt.Errorf("unsupported handling alg %q", a.Alg)
		}
		return &cfg, nil
	}
	return nil, fmt.Errorf("unknown assertion kind %q", a.Kind)
}

func parseRSAKey(p string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(p))
	if block == nil {
		return nil, errors.New("key_pem is not PEM")
	}
	if k, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return k, nil
	}
	k, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parse RSA key: %w", err)
	}
	rk, ok := k.(*rsa.PrivateKey)
	if !ok {
		return nil, errors.New("key_pem is not an RSA key")
	}
	return rk, nil
}

// kasInfos maps kas/split onto WithKasInformation. The SDK numbers splits "s-<i>"
// itself (one KAO each, none for a single KAS) and its split plan is unexported,
// so only that layout can be written.
func kasInfos(j job) ([]sdk.KASInfo, error) {
	if len(j.KAS) == 0 {
		return nil, errors.New("need kas or attributes")
	}
	order := make([]int, len(j.KAS))
	for i := range order {
		order[i] = i
	}
	if len(j.Split) > 0 {
		if len(j.Split) != len(j.KAS) {
			return nil, errors.New("split must name every kas exactly once")
		}
		seen := map[int]bool{}
		for i, s := range j.Split {
			want := ""
			if len(j.Split) > 1 {
				want = fmt.Sprintf("s-%d", i)
			}
			if s.SID != want {
				return nil, fmt.Errorf("Go SDK %s writes split id %q at position %d, not %q", sdkVersion(), want, i, s.SID)
			}
			if s.KAS == nil {
				return nil, errors.New("split entry missing kas")
			}
			k := *s.KAS
			if k < 0 || k >= len(j.KAS) || seen[k] {
				return nil, errors.New("split must name every kas exactly once")
			}
			seen[k] = true
			order[i] = k
		}
	}
	infos := make([]sdk.KASInfo, 0, len(order))
	for _, idx := range order {
		k := j.KAS[idx]
		infos = append(infos, sdk.KASInfo{URL: k.URL, KID: k.KID, Algorithm: k.Alg})
	}
	return infos, nil
}

func options(j job) ([]sdk.TDFOption, error) {
	var opts []sdk.TDFOption
	if len(j.Attributes) > 0 {
		opts = append(opts, sdk.WithDataAttributes(j.Attributes...), sdk.WithAutoconfigure(true))
	} else {
		infos, err := kasInfos(j)
		if err != nil {
			return nil, err
		}
		opts = append(opts, sdk.WithAutoconfigure(false), sdk.WithKasInformation(infos...))
	}
	if j.SegmentSize != nil {
		// WithSegmentSize clamps out-of-range values instead of failing.
		if *j.SegmentSize < minSegmentSize || *j.SegmentSize > maxSegmentSize {
			return nil, fmt.Errorf("segment_size %d outside [%d, %d]", *j.SegmentSize, minSegmentSize, maxSegmentSize)
		}
		opts = append(opts, sdk.WithSegmentSize(*j.SegmentSize))
	}
	if j.MimeType != nil {
		opts = append(opts, sdk.WithMimeType(*j.MimeType))
	}
	if j.EncryptedMetadata != nil {
		opts = append(opts, sdk.WithMetaData(*j.EncryptedMetadata))
	}
	if j.TargetMode != nil {
		opts = append(opts, sdk.WithTargetMode(*j.TargetMode))
	}
	var cfgs []sdk.AssertionConfig
	ids := map[string]bool{}
	for _, a := range j.Assertions {
		cfg, err := assertionConfig(a)
		if err != nil {
			return nil, err
		}
		id := sdk.SystemMetadataAssertionID
		if cfg != nil {
			id = cfg.ID
		}
		if ids[id] {
			return nil, fmt.Errorf("duplicate assertion id %q", id)
		}
		ids[id] = true
		if cfg == nil {
			opts = append(opts, sdk.WithSystemMetadataAssertion())
		} else {
			cfgs = append(cfgs, *cfg)
		}
	}
	if len(cfgs) > 0 {
		opts = append(opts, sdk.WithAssertions(cfgs...))
	}
	return opts, nil
}

func write(ctx context.Context, s *sdk.SDK, j job) error {
	opts, err := options(j)
	if err != nil {
		return err
	}
	plain, err := os.ReadFile(j.Plaintext)
	if err != nil {
		return err
	}
	var out bytes.Buffer
	if _, err := s.CreateTDFContext(ctx, &out, bytes.NewReader(plain), opts...); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(j.Out), 0o755); err != nil {
		return err
	}
	return os.WriteFile(j.Out, out.Bytes(), 0o644)
}

func run(path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var jobs []job
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&jobs); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}

	platform := os.Getenv("PLATFORMURL")
	if platform == "" || os.Getenv("CLIENTID") == "" || os.Getenv("CLIENTSECRET") == "" {
		return errors.New("PLATFORMURL, CLIENTID and CLIENTSECRET must be set")
	}
	s, err := sdk.New(platform,
		sdk.WithInsecurePlaintextConn(),
		sdk.WithClientCredentials(os.Getenv("CLIENTID"), os.Getenv("CLIENTSECRET"), nil),
	)
	if err != nil {
		return err
	}
	defer s.Close()

	ctx := context.Background()
	version := sdkVersion()
	failed := false
	for _, j := range jobs {
		if err := write(ctx, s, j); err != nil {
			fmt.Fprintf(os.Stderr, "job %s: %v\n", j.Out, err)
			failed = true
			continue
		}
		line, _ := json.Marshal(map[string]string{"out": j.Out, "sdk": "go", "version": version})
		fmt.Println(string(line))
	}
	if failed {
		return errors.New("one or more jobs failed")
	}
	return nil
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: writer <jobs.json>")
		os.Exit(2)
	}
	if err := run(os.Args[1]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
