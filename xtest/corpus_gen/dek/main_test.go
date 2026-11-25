package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/opentdf/platform/lib/ocrypto"
)

var algs = []string{
	"rsa:2048",
	"ec:secp256r1",
	"hpqt:xwing",
	"hpqt:secp256r1-mlkem768",
	"hpqt:secp384r1-mlkem1024",
	"mlkem:768",
	"mlkem:1024",
}

type keyFile struct {
	Alg        string `json:"alg"`
	PrivateKey string `json:"privateKey"`
	Cert       string `json:"cert"`
}

type policyBinding struct {
	Alg  string `json:"alg"`
	Hash string `json:"hash"`
}

// testKAO mirrors sdk.KeyAccess in the platform's sdk/manifest.go.
type testKAO struct {
	KeyType            string        `json:"type"`
	KasURL             string        `json:"url"`
	Protocol           string        `json:"protocol"`
	WrappedKey         string        `json:"wrappedKey"`
	PolicyBinding      policyBinding `json:"policyBinding"`
	EncryptedMetadata  string        `json:"encryptedMetadata,omitempty"`
	KID                string        `json:"kid,omitempty"`
	SplitID            string        `json:"sid,omitempty"`
	SchemaVersion      string        `json:"schemaVersion,omitempty"`
	EphemeralPublicKey string        `json:"ephemeralPublicKey,omitempty"`
}

func runCmd(args ...string) (string, error) {
	var out bytes.Buffer
	err := run(args, &out)
	return out.String(), err
}

func genKey(t *testing.T, alg string) keyFile {
	t.Helper()
	out, err := runCmd("keygen", "--alg", alg)
	if err != nil {
		t.Fatalf("keygen %s: %v", alg, err)
	}
	var k keyFile
	if err := json.Unmarshal([]byte(out), &k); err != nil {
		t.Fatalf("keygen %s output is not JSON: %v\n%s", alg, err, out)
	}
	if k.Alg != alg || k.PrivateKey == "" || k.Cert == "" {
		t.Fatalf("keygen %s: incomplete output %+v", alg, k)
	}
	return k
}

func writeTemp(t *testing.T, name string, data []byte) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(p, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func randomDEK(t *testing.T) []byte {
	t.Helper()
	dek := make([]byte, 32)
	if _, err := rand.Read(dek); err != nil {
		t.Fatal(err)
	}
	return dek
}

// wrapLikeSDK builds a KAO for dek the way the platform's sdk/tdf.go
// createKeyAccess does.
func wrapLikeSDK(t *testing.T, alg, kasPub string, dek []byte) []byte {
	t.Helper()
	k := testKAO{
		KasURL:        "http://localhost:8585",
		Protocol:      "kas",
		PolicyBinding: policyBinding{Alg: "HS256", Hash: "aGFzaA=="},
		KID:           "test",
		SchemaVersion: "1.0",
	}
	kt := ocrypto.KeyType(alg)
	switch {
	case ocrypto.IsKEMKeyType(kt):
		der, err := ocrypto.WrapDEK(kt, kasPub, dek)
		if err != nil {
			t.Fatalf("WrapDEK: %v", err)
		}
		k.KeyType = "hybrid-wrapped"
		if ocrypto.IsMLKEMKeyType(kt) {
			k.KeyType = "mlkem-wrapped"
		}
		k.WrappedKey = string(ocrypto.Base64Encode(der))
	case ocrypto.IsECKeyType(kt):
		mode, err := ocrypto.ECKeyTypeToMode(kt)
		if err != nil {
			t.Fatal(err)
		}
		eph, err := ocrypto.NewECKeyPair(mode)
		if err != nil {
			t.Fatal(err)
		}
		ephPub, err := eph.PublicKeyInPemFormat()
		if err != nil {
			t.Fatal(err)
		}
		ephPriv, err := eph.PrivateKeyInPemFormat()
		if err != nil {
			t.Fatal(err)
		}
		shared, err := ocrypto.ComputeECDHKey([]byte(ephPriv), []byte(kasPub))
		if err != nil {
			t.Fatalf("ComputeECDHKey: %v", err)
		}
		salt := sha256.Sum256([]byte("TDF"))
		sessionKey, err := ocrypto.CalculateHKDF(salt[:], shared)
		if err != nil {
			t.Fatal(err)
		}
		gcm, err := ocrypto.NewAESGcm(sessionKey)
		if err != nil {
			t.Fatal(err)
		}
		wrapped, err := gcm.Encrypt(dek)
		if err != nil {
			t.Fatal(err)
		}
		k.KeyType = "ec-wrapped"
		k.WrappedKey = string(ocrypto.Base64Encode(wrapped))
		k.EphemeralPublicKey = ephPub
	default:
		enc, err := ocrypto.FromPublicPEM(kasPub)
		if err != nil {
			t.Fatalf("FromPublicPEM: %v", err)
		}
		wrapped, err := enc.Encrypt(dek)
		if err != nil {
			t.Fatal(err)
		}
		k.KeyType = "wrapped"
		k.WrappedKey = string(ocrypto.Base64Encode(wrapped))
	}
	b, err := json.Marshal(k)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestRoundTrip(t *testing.T) {
	for _, alg := range algs {
		t.Run(alg, func(t *testing.T) {
			k := genKey(t, alg)
			dek := randomDEK(t)
			priv := writeTemp(t, "private.pem", []byte(k.PrivateKey))
			kao := writeTemp(t, "kao.json", wrapLikeSDK(t, alg, k.Cert, dek))
			out, err := runCmd("unwrap", "--private", priv, "--kao", kao)
			if err != nil {
				t.Fatalf("unwrap: %v", err)
			}
			if want := hex.EncodeToString(dek) + "\n"; out != want {
				t.Fatalf("unwrap = %q, want %q", out, want)
			}
		})
	}
}

func TestUnwrapWrongKeyFails(t *testing.T) {
	for _, alg := range algs {
		t.Run(alg, func(t *testing.T) {
			owner, other := genKey(t, alg), genKey(t, alg)
			kaoJSON := wrapLikeSDK(t, alg, owner.Cert, randomDEK(t))
			var parsed testKAO
			if err := json.Unmarshal(kaoJSON, &parsed); err != nil {
				t.Fatal(err)
			}
			priv := writeTemp(t, "private.pem", []byte(other.PrivateKey))
			kao := writeTemp(t, "kao.json", kaoJSON)
			out, err := runCmd("unwrap", "--private", priv, "--kao", kao)
			if err == nil {
				t.Fatalf("unwrap with the wrong key succeeded: %q", out)
			}
			if !strings.Contains(err.Error(), parsed.KeyType) {
				t.Fatalf("error %q does not name KAO type %q", err, parsed.KeyType)
			}
		})
	}
}

func TestUnwrapUnsupportedType(t *testing.T) {
	k := genKey(t, "rsa:2048")
	kaoJSON := wrapLikeSDK(t, "rsa:2048", k.Cert, randomDEK(t))
	kaoJSON = bytes.Replace(kaoJSON, []byte(`"type":"wrapped"`), []byte(`"type":"remote"`), 1)
	priv := writeTemp(t, "private.pem", []byte(k.PrivateKey))
	kao := writeTemp(t, "kao.json", kaoJSON)
	_, err := runCmd("unwrap", "--private", priv, "--kao", kao)
	if err == nil || !strings.Contains(err.Error(), "remote") {
		t.Fatalf("want an error naming type remote, got %v", err)
	}
}

func TestPub(t *testing.T) {
	for _, alg := range algs {
		t.Run(alg, func(t *testing.T) {
			k := genKey(t, alg)
			priv := writeTemp(t, "private.pem", []byte(k.PrivateKey))
			out, err := runCmd("pub", "--private", priv)
			if err != nil {
				t.Fatalf("pub: %v", err)
			}
			want := k.Cert
			if strings.HasPrefix(alg, "rsa:") || strings.HasPrefix(alg, "ec:") {
				want = spkiPEMOfCert(t, k.Cert)
			}
			if out != want {
				t.Fatalf("pub = %q, want %q", out, want)
			}
		})
	}
}

// pub reads the PKCS#1 and SEC 1 encodings that unwrap reads.
func TestPubLegacyEncodings(t *testing.T) {
	for _, alg := range []string{"rsa:2048", "ec:secp256r1"} {
		t.Run(alg, func(t *testing.T) {
			k := genKey(t, alg)
			block, _ := pem.Decode([]byte(k.PrivateKey))
			key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
			if err != nil {
				t.Fatal(err)
			}
			var legacy *pem.Block
			switch key := key.(type) {
			case *rsa.PrivateKey:
				legacy = &pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)}
			case *ecdsa.PrivateKey:
				der, err := x509.MarshalECPrivateKey(key)
				if err != nil {
					t.Fatal(err)
				}
				legacy = &pem.Block{Type: "EC PRIVATE KEY", Bytes: der}
			default:
				t.Fatalf("unexpected key type %T", key)
			}
			priv := writeTemp(t, "private.pem", pem.EncodeToMemory(legacy))
			out, err := runCmd("pub", "--private", priv)
			if err != nil {
				t.Fatalf("pub %s: %v", legacy.Type, err)
			}
			if want := spkiPEMOfCert(t, k.Cert); out != want {
				t.Fatalf("pub = %q, want %q", out, want)
			}
		})
	}
}

func TestPubRejectsUnknownBlock(t *testing.T) {
	k := genKey(t, "rsa:2048")
	relabelled := strings.Replace(k.PrivateKey, "PRIVATE KEY", "OPENSSH PRIVATE KEY", 2)
	priv := writeTemp(t, "private.pem", []byte(relabelled))
	if out, err := runCmd("pub", "--private", priv); err == nil {
		t.Fatalf("pub of an OPENSSH PRIVATE KEY block succeeded: %q", out)
	}
}

func spkiPEMOfCert(t *testing.T, certPEM string) string {
	t.Helper()
	cert := parseCert(t, certPEM)
	der, err := x509.MarshalPKIXPublicKey(cert.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
}

func parseCert(t *testing.T, certPEM string) *x509.Certificate {
	t.Helper()
	block, _ := pem.Decode([]byte(certPEM))
	if block == nil || block.Type != "CERTIFICATE" {
		t.Fatalf("not a certificate PEM: %q", certPEM)
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		t.Fatal(err)
	}
	return cert
}

func TestKeygenCert(t *testing.T) {
	for _, alg := range []string{"rsa:2048", "ec:secp256r1"} {
		t.Run(alg, func(t *testing.T) {
			cert := parseCert(t, genKey(t, alg).Cert)
			if cert.Subject.CommonName != "corpus" {
				t.Errorf("CN = %q, want corpus", cert.Subject.CommonName)
			}
			if err := cert.CheckSignature(cert.SignatureAlgorithm, cert.RawTBSCertificate, cert.Signature); err != nil {
				t.Errorf("not self-signed: %v", err)
			}
			if minEnd := time.Now().AddDate(9, 0, 0); cert.NotAfter.Before(minEnd) {
				t.Errorf("NotAfter %v is before %v", cert.NotAfter, minEnd)
			}
		})
	}
}
