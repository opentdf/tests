package main

import (
	"context"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/opentdf/platform/protocol/go/policy"
	"github.com/opentdf/platform/protocol/go/policy/attributes"
	"github.com/opentdf/platform/sdk"
	exptdf "github.com/opentdf/platform/sdk/experimental/tdf"
)

const segmentSize = 2 * 1024 * 1024 // 2 MiB, matches standard SDK default

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: exp-go-sdk <encrypt|decrypt|supports> ...")
		os.Exit(1)
	}
	switch os.Args[1] {
	case "encrypt":
		if err := doEncrypt(os.Args[2:]); err != nil {
			fmt.Fprintf(os.Stderr, "encrypt error: %v\n", err)
			os.Exit(1)
		}
	case "decrypt":
		if err := doDecrypt(os.Args[2:]); err != nil {
			fmt.Fprintf(os.Stderr, "decrypt error: %v\n", err)
			os.Exit(1)
		}
	case "supports":
		if len(os.Args) < 3 {
			fmt.Fprintln(os.Stderr, "usage: exp-go-sdk supports <feature>")
			os.Exit(2)
		}
		doSupports(os.Args[2])
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", os.Args[1])
		os.Exit(1)
	}
}

// ----- supports -----

func doSupports(feature string) {
	switch feature {
	case "assertions",
		"assertion_verification",
		"autoconfigure",
		"ns_grants",
		"ecwrap",
		"hexless",
		"connectrpc",
		"kasallowlist",
		"better-messages-2024":
		os.Exit(0)
	default:
		// Unsupported: hexaflexible, obligations, key_management, bulk_rewrap
		fmt.Fprintf(os.Stderr, "unsupported feature: %s\n", feature)
		os.Exit(1)
	}
}

// ----- encrypt -----

type encryptFlags struct {
	inputFile         string
	output            string
	platformEndpoint  string
	clientID          string
	clientSecret      string
	tokenEndpoint     string
	attributes        string
	assertions        string
	mimeType          string
	wrappingAlgorithm string
	policyMode        string
	targetMode        string
	tlsNoVerify       bool
}

func parseEncryptFlags(args []string) (*encryptFlags, error) {
	f := &encryptFlags{
		mimeType: "application/octet-stream",
	}
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--output", "-o":
			i++
			f.output = args[i]
		case "--platform-endpoint":
			i++
			f.platformEndpoint = args[i]
		case "--client-id":
			i++
			f.clientID = args[i]
		case "--client-secret":
			i++
			f.clientSecret = args[i]
		case "--token-endpoint":
			i++
			f.tokenEndpoint = args[i]
		case "--attributes":
			i++
			f.attributes = args[i]
		case "--assertions":
			i++
			f.assertions = args[i]
		case "--mime-type":
			i++
			f.mimeType = args[i]
		case "--wrapping-algorithm":
			i++
			f.wrappingAlgorithm = args[i]
		case "--policy-mode":
			i++
			f.policyMode = args[i]
		case "--target-mode":
			i++
			f.targetMode = args[i]
		case "--tls-no-verify":
			f.tlsNoVerify = true
		default:
			if f.inputFile == "" && !strings.HasPrefix(args[i], "-") {
				f.inputFile = args[i]
			} else {
				return nil, fmt.Errorf("unknown flag or duplicate input: %s", args[i])
			}
		}
	}
	if f.inputFile == "" {
		return nil, fmt.Errorf("input file required")
	}
	if f.output == "" {
		return nil, fmt.Errorf("--output required")
	}
	return f, nil
}

func doEncrypt(args []string) error {
	f, err := parseEncryptFlags(args)
	if err != nil {
		return err
	}

	ctx := context.Background()

	// Build SDK client
	client, err := newSDKClient(f.platformEndpoint, f.clientID, f.clientSecret, f.tokenEndpoint, f.tlsNoVerify)
	if err != nil {
		return fmt.Errorf("creating SDK client: %w", err)
	}
	defer client.Close()

	// Get base KAS key — try well-known config first, fall back to direct KAS query
	baseKey, err := client.GetBaseKey(ctx)
	if err != nil {
		fmt.Fprintf(os.Stderr, "GetBaseKey failed (%v), falling back to direct KAS public key fetch\n", err)
		baseKey, err = fetchKASPublicKey(f.platformEndpoint, f.tlsNoVerify)
		if err != nil {
			return fmt.Errorf("fetching KAS public key: %w", err)
		}
	}

	// Resolve attributes if specified
	var attrValues []*policy.Value
	if f.attributes != "" {
		attrValues, err = resolveAttributes(ctx, client, f.attributes)
		if err != nil {
			return fmt.Errorf("resolving attributes: %w", err)
		}
	}

	// Parse assertions if specified
	var assertionConfigs []exptdf.AssertionConfig
	if f.assertions != "" {
		assertionConfigs, err = parseAssertions(f.assertions)
		if err != nil {
			return fmt.Errorf("parsing assertions: %w", err)
		}
	}

	// Create experimental writer
	writer, err := exptdf.NewWriter(ctx,
		exptdf.WithIntegrityAlgorithm(exptdf.HS256),
		exptdf.WithSegmentIntegrityAlgorithm(exptdf.HS256),
	)
	if err != nil {
		return fmt.Errorf("creating writer: %w", err)
	}

	// Read input and write segments
	data, err := os.ReadFile(f.inputFile)
	if err != nil {
		return fmt.Errorf("reading input file: %w", err)
	}

	segIdx := 0
	for offset := 0; offset < len(data); offset += segmentSize {
		end := offset + segmentSize
		if end > len(data) {
			end = len(data)
		}
		if _, err := writer.WriteSegment(ctx, segIdx, data[offset:end]); err != nil {
			return fmt.Errorf("writing segment %d: %w", segIdx, err)
		}
		segIdx++
	}
	// Handle empty file: write one empty segment
	if len(data) == 0 {
		if _, err := writer.WriteSegment(ctx, 0, []byte{}); err != nil {
			return fmt.Errorf("writing empty segment: %w", err)
		}
	}

	// Build finalize options
	finalizeOpts := []exptdf.Option[*exptdf.WriterFinalizeConfig]{
		exptdf.WithDefaultKAS(baseKey),
	}
	if len(attrValues) > 0 {
		finalizeOpts = append(finalizeOpts, exptdf.WithAttributeValues(attrValues))
	}
	if len(assertionConfigs) > 0 {
		finalizeOpts = append(finalizeOpts, exptdf.WithAssertions(assertionConfigs...))
	}
	if f.mimeType != "" {
		finalizeOpts = append(finalizeOpts, exptdf.WithPayloadMimeType(f.mimeType))
	}

	// Finalize
	result, err := writer.Finalize(ctx, finalizeOpts...)
	if err != nil {
		return fmt.Errorf("finalizing TDF: %w", err)
	}

	// Write output
	if err := os.WriteFile(f.output, result.Data, 0o644); err != nil {
		return fmt.Errorf("writing output: %w", err)
	}

	return nil
}

// ----- decrypt -----

type decryptFlags struct {
	inputFile                  string
	output                     string
	platformEndpoint           string
	clientID                   string
	clientSecret               string
	tokenEndpoint              string
	wrappingAlgorithm          string
	assertionVerificationKeys  string
	noVerifyAssertions         bool
	kasAllowlist               string
	tlsNoVerify                bool
	ignoreKasAllowlist         bool
}

func parseDecryptFlags(args []string) (*decryptFlags, error) {
	f := &decryptFlags{}
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--output", "-o":
			i++
			f.output = args[i]
		case "--platform-endpoint":
			i++
			f.platformEndpoint = args[i]
		case "--client-id":
			i++
			f.clientID = args[i]
		case "--client-secret":
			i++
			f.clientSecret = args[i]
		case "--token-endpoint":
			i++
			f.tokenEndpoint = args[i]
		case "--wrapping-algorithm":
			i++
			f.wrappingAlgorithm = args[i]
		case "--assertion-verification-keys":
			i++
			f.assertionVerificationKeys = args[i]
		case "--no-verify-assertions":
			f.noVerifyAssertions = true
		case "--kas-allowlist":
			i++
			f.kasAllowlist = args[i]
		case "--tls-no-verify":
			f.tlsNoVerify = true
		case "--ignore-kas-allowlist":
			f.ignoreKasAllowlist = true
		default:
			if f.inputFile == "" && !strings.HasPrefix(args[i], "-") {
				f.inputFile = args[i]
			} else {
				return nil, fmt.Errorf("unknown flag or duplicate input: %s", args[i])
			}
		}
	}
	if f.inputFile == "" {
		return nil, fmt.Errorf("input file required")
	}
	if f.output == "" {
		return nil, fmt.Errorf("--output required")
	}
	return f, nil
}

func doDecrypt(args []string) error {
	f, err := parseDecryptFlags(args)
	if err != nil {
		return err
	}

	// Build SDK client
	client, err := newSDKClient(f.platformEndpoint, f.clientID, f.clientSecret, f.tokenEndpoint, f.tlsNoVerify)
	if err != nil {
		return fmt.Errorf("creating SDK client: %w", err)
	}
	defer client.Close()

	// Open input file
	inFile, err := os.Open(f.inputFile)
	if err != nil {
		return fmt.Errorf("opening input: %w", err)
	}
	defer inFile.Close()

	// Build reader options
	var readerOpts []sdk.TDFReaderOption
	if f.noVerifyAssertions {
		readerOpts = append(readerOpts, sdk.WithDisableAssertionVerification(true))
	}
	if f.assertionVerificationKeys != "" {
		keys, err := loadAssertionVerificationKeys(f.assertionVerificationKeys)
		if err != nil {
			return fmt.Errorf("loading assertion verification keys: %w", err)
		}
		readerOpts = append(readerOpts, sdk.WithAssertionVerificationKeys(keys))
	}
	if f.kasAllowlist != "" {
		list := strings.Split(f.kasAllowlist, ",")
		readerOpts = append(readerOpts, sdk.WithKasAllowlist(list))
	} else if f.ignoreKasAllowlist {
		readerOpts = append(readerOpts, sdk.WithKasAllowlist([]string{"*"}))
	}

	// Load and decrypt TDF
	reader, err := client.LoadTDF(inFile, readerOpts...)
	if err != nil {
		return fmt.Errorf("loading TDF: %w", err)
	}

	// Write decrypted output
	outFile, err := os.Create(f.output)
	if err != nil {
		return fmt.Errorf("creating output: %w", err)
	}
	defer outFile.Close()

	if _, err := io.Copy(outFile, reader); err != nil {
		return fmt.Errorf("writing decrypted data: %w", err)
	}

	return nil
}

// ----- helpers -----

func newSDKClient(endpoint, clientID, clientSecret, tokenEndpoint string, tlsNoVerify bool) (*sdk.SDK, error) {
	opts := []sdk.Option{
		sdk.WithClientCredentials(clientID, clientSecret, nil),
	}
	if tokenEndpoint != "" {
		opts = append(opts, sdk.WithTokenEndpoint(tokenEndpoint))
	}
	if tlsNoVerify {
		opts = append(opts, sdk.WithInsecureSkipVerifyConn())
	}
	if strings.HasPrefix(endpoint, "http://") {
		opts = append(opts, sdk.WithInsecurePlaintextConn())
	}
	return sdk.New(endpoint, opts...)
}

// kasPublicKeyResponse matches the JSON returned by the KAS /kas/v2/kas_public_key endpoint.
type kasPublicKeyResponse struct {
	PublicKey string `json:"publicKey"`
	KID       string `json:"kid"`
}

func fetchKASPublicKey(platformEndpoint string, tlsNoVerify bool) (*policy.SimpleKasKey, error) {
	kasURL := strings.TrimSuffix(platformEndpoint, "/") + "/kas"
	pubKeyURL := kasURL + "/v2/kas_public_key?algorithm=rsa:2048"

	httpClient := &http.Client{}
	if tlsNoVerify {
		httpClient.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12, InsecureSkipVerify: true}, //nolint:gosec // user-requested TLS skip
		}
	}

	resp, err := httpClient.Get(pubKeyURL) //nolint:gosec // URL is from trusted platform endpoint
	if err != nil {
		return nil, fmt.Errorf("GET %s: %w", pubKeyURL, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("GET %s returned %d: %s", pubKeyURL, resp.StatusCode, string(body))
	}

	var pkResp kasPublicKeyResponse
	if err := json.NewDecoder(resp.Body).Decode(&pkResp); err != nil {
		return nil, fmt.Errorf("decoding KAS public key response: %w", err)
	}

	return &policy.SimpleKasKey{
		KasUri: kasURL,
		PublicKey: &policy.SimpleKasPublicKey{
			Algorithm: policy.Algorithm_ALGORITHM_RSA_2048,
			Kid:       pkResp.KID,
			Pem:       pkResp.PublicKey,
		},
	}, nil
}

func resolveAttributes(ctx context.Context, client *sdk.SDK, attrStr string) ([]*policy.Value, error) {
	fqns := strings.Split(attrStr, ",")
	for i := range fqns {
		fqns[i] = strings.TrimSpace(fqns[i])
	}

	resp, err := client.Attributes.GetAttributeValuesByFqns(ctx, &attributes.GetAttributeValuesByFqnsRequest{
		Fqns: fqns,
	})
	if err != nil {
		return nil, fmt.Errorf("GetAttributeValuesByFqns: %w", err)
	}

	var values []*policy.Value
	for _, fqn := range fqns {
		av, ok := resp.GetFqnAttributeValues()[fqn]
		if !ok {
			return nil, fmt.Errorf("attribute not found in response: %s", fqn)
		}
		v := av.GetValue()
		if v == nil {
			return nil, fmt.Errorf("no value for attribute: %s", fqn)
		}
		values = append(values, v)
	}
	return values, nil
}

// assertionJSON matches the JSON format used by xtest assertion fixtures.
type assertionJSON struct {
	ID             string `json:"id"`
	Type           string `json:"type"`
	Scope          string `json:"scope"`
	AppliesToState string `json:"appliesToState"`
	Statement      struct {
		Format string `json:"format"`
		Schema string `json:"schema"`
		Value  string `json:"value"`
	} `json:"statement"`
	SigningKey *struct {
		Alg string `json:"alg"`
		Key string `json:"key"`
	} `json:"signingKey,omitempty"`
}

func parseAssertions(input string) ([]exptdf.AssertionConfig, error) {
	var raw []byte
	// Check if input is a file path
	if _, err := os.Stat(input); err == nil {
		raw, err = os.ReadFile(input)
		if err != nil {
			return nil, fmt.Errorf("reading assertions file: %w", err)
		}
	} else {
		raw = []byte(input)
	}

	var ajList []assertionJSON
	if err := json.Unmarshal(raw, &ajList); err != nil {
		return nil, fmt.Errorf("unmarshaling assertions JSON: %w", err)
	}

	var configs []exptdf.AssertionConfig
	for _, aj := range ajList {
		cfg := exptdf.AssertionConfig{
			ID:             aj.ID,
			Type:           exptdf.AssertionType(aj.Type),
			Scope:          exptdf.Scope(aj.Scope),
			AppliesToState: exptdf.AppliesToState(aj.AppliesToState),
			Statement: exptdf.Statement{
				Format: aj.Statement.Format,
				Schema: aj.Statement.Schema,
				Value:  aj.Statement.Value,
			},
		}
		if aj.SigningKey != nil && aj.SigningKey.Key != "" {
			key, err := loadSigningKey(aj.SigningKey.Alg, aj.SigningKey.Key)
			if err != nil {
				return nil, fmt.Errorf("loading signing key for assertion %s: %w", aj.ID, err)
			}
			cfg.SigningKey = key
		}
		configs = append(configs, cfg)
	}
	return configs, nil
}

func loadSigningKey(alg, keyData string) (exptdf.AssertionKey, error) {
	switch exptdf.AssertionKeyAlg(alg) {
	case exptdf.AssertionKeyAlgRS256:
		key, err := parseRSAPrivateKey(keyData)
		if err != nil {
			return exptdf.AssertionKey{}, err
		}
		return exptdf.AssertionKey{Alg: exptdf.AssertionKeyAlgRS256, Key: key}, nil
	case exptdf.AssertionKeyAlgHS256:
		return exptdf.AssertionKey{Alg: exptdf.AssertionKeyAlgHS256, Key: []byte(keyData)}, nil
	default:
		return exptdf.AssertionKey{}, fmt.Errorf("unsupported signing algorithm: %s", alg)
	}
}

func parseRSAPrivateKey(keyData string) (*rsa.PrivateKey, error) {
	// Try as file path first
	if data, err := os.ReadFile(keyData); err == nil {
		keyData = string(data)
	}
	block, _ := pem.Decode([]byte(keyData))
	if block == nil {
		return nil, fmt.Errorf("failed to decode PEM block")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		// Try PKCS1
		key2, err2 := x509.ParsePKCS1PrivateKey(block.Bytes)
		if err2 != nil {
			return nil, fmt.Errorf("failed to parse private key (PKCS8: %v, PKCS1: %v)", err, err2)
		}
		return key2, nil
	}
	rsaKey, ok := key.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("key is not RSA")
	}
	return rsaKey, nil
}

// assertionVerificationKeysJSON matches the JSON format used by xtest.
type assertionVerificationKeysJSON struct {
	DefaultKey *assertionKeyJSON            `json:"defaultKey,omitempty"`
	Keys       map[string]assertionKeyJSON  `json:"keys,omitempty"`
}

type assertionKeyJSON struct {
	Alg string `json:"alg"`
	Key string `json:"key"`
}

func loadAssertionVerificationKeys(input string) (sdk.AssertionVerificationKeys, error) {
	var raw []byte
	var err error

	// Try as file path first
	if _, statErr := os.Stat(input); statErr == nil {
		raw, err = os.ReadFile(input)
		if err != nil {
			return sdk.AssertionVerificationKeys{}, fmt.Errorf("reading verification keys file: %w", err)
		}
	} else {
		raw = []byte(input)
	}

	var vkJSON assertionVerificationKeysJSON
	if err := json.Unmarshal(raw, &vkJSON); err != nil {
		return sdk.AssertionVerificationKeys{}, fmt.Errorf("unmarshaling verification keys JSON: %w", err)
	}

	result := sdk.AssertionVerificationKeys{
		Keys: make(map[string]sdk.AssertionKey),
	}

	if vkJSON.DefaultKey != nil {
		k, err := loadSDKAssertionKey(vkJSON.DefaultKey.Alg, vkJSON.DefaultKey.Key)
		if err != nil {
			return sdk.AssertionVerificationKeys{}, fmt.Errorf("loading default verification key: %w", err)
		}
		result.DefaultKey = k
	}

	for id, kj := range vkJSON.Keys {
		k, err := loadSDKAssertionKey(kj.Alg, kj.Key)
		if err != nil {
			return sdk.AssertionVerificationKeys{}, fmt.Errorf("loading verification key for %s: %w", id, err)
		}
		result.Keys[id] = k
	}

	return result, nil
}

func loadSDKAssertionKey(alg, keyData string) (sdk.AssertionKey, error) {
	switch sdk.AssertionKeyAlg(alg) {
	case sdk.AssertionKeyAlgRS256:
		key, err := parseRSAPrivateKey(keyData)
		if err != nil {
			return sdk.AssertionKey{}, err
		}
		return sdk.AssertionKey{Alg: sdk.AssertionKeyAlgRS256, Key: key}, nil
	case sdk.AssertionKeyAlgHS256:
		return sdk.AssertionKey{Alg: sdk.AssertionKeyAlgHS256, Key: []byte(keyData)}, nil
	default:
		return sdk.AssertionKey{}, fmt.Errorf("unsupported verification algorithm: %s", alg)
	}
}
