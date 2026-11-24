// Command dek generates stable KAS keys and unwraps TDF key access objects
// offline with the platform's lib/ocrypto, for the corpus generator.
//
// From xtest/: go -C corpus_gen/dek run . <keygen|pub|unwrap> [flags]
package main

import (
	"crypto"
	"crypto/ecdsa"
	"crypto/mlkem"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io"
	"math/big"
	"os"
	"time"

	"github.com/cloudflare/circl/kem/xwing"
	"github.com/opentdf/platform/lib/ocrypto"
)

const usage = `usage:
  dek keygen --alg <alg>
  dek pub --private <pem-file>
  dek unwrap --private <pem-file> --kao <kao-json-file>`

// KAO types written by the platform SDK (sdk/tdf.go).
const (
	kaoWrapped       = "wrapped"
	kaoECWrapped     = "ec-wrapped"
	kaoHybridWrapped = "hybrid-wrapped"
	kaoMLKEMWrapped  = "mlkem-wrapped"
)

// NIST hybrid private keys are mlkemSeed || ECPrivateKey DER (ocrypto hybrid_nist.go).
const mlkemSeedSize = 64

type keyMaterial struct {
	Alg        string `json:"alg"`
	PrivateKey string `json:"privateKey"`
	Cert       string `json:"cert"`
}

// keyAccess holds the KAO fields unwrap reads, under sdk.KeyAccess's JSON names.
type keyAccess struct {
	Type               string `json:"type"`
	WrappedKey         string `json:"wrappedKey"`
	EphemeralPublicKey string `json:"ephemeralPublicKey"`
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "dek:", err)
		os.Exit(1)
	}
}

func run(args []string, stdout io.Writer) error {
	if len(args) == 0 {
		return errors.New(usage)
	}
	fs := flag.NewFlagSet(args[0], flag.ContinueOnError)
	switch args[0] {
	case "keygen":
		alg := fs.String("alg", "", "key algorithm, e.g. rsa:2048, ec:secp256r1, hpqt:xwing, mlkem:768")
		if err := parseFlags(fs, args[1:], "alg"); err != nil {
			return err
		}
		km, err := keygen(*alg)
		if err != nil {
			return err
		}
		out, err := json.Marshal(km)
		if err != nil {
			return err
		}
		_, err = fmt.Fprintln(stdout, string(out))
		return err
	case "pub":
		priv := fs.String("private", "", "private key PEM file")
		if err := parseFlags(fs, args[1:], "private"); err != nil {
			return err
		}
		privPEM, err := os.ReadFile(*priv)
		if err != nil {
			return err
		}
		pub, err := publicPEM(string(privPEM))
		if err != nil {
			return err
		}
		_, err = io.WriteString(stdout, pub)
		return err
	case "unwrap":
		priv := fs.String("private", "", "private key PEM file")
		kao := fs.String("kao", "", "file holding one keyAccess object from a TDF manifest")
		if err := parseFlags(fs, args[1:], "private", "kao"); err != nil {
			return err
		}
		privPEM, err := os.ReadFile(*priv)
		if err != nil {
			return err
		}
		kaoJSON, err := os.ReadFile(*kao)
		if err != nil {
			return err
		}
		key, err := unwrap(string(privPEM), kaoJSON)
		if err != nil {
			return err
		}
		_, err = fmt.Fprintln(stdout, hex.EncodeToString(key))
		return err
	default:
		return fmt.Errorf("unknown command %q\n%s", args[0], usage)
	}
}

func parseFlags(fs *flag.FlagSet, args []string, required ...string) error {
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() > 0 {
		return fmt.Errorf("%s: unexpected arguments %q", fs.Name(), fs.Args())
	}
	for _, name := range required {
		if fs.Lookup(name).Value.String() == "" {
			return fmt.Errorf("%s: --%s is required", fs.Name(), name)
		}
	}
	return nil
}

// keygen makes a key pair with ocrypto.NewKeyPair. RSA and EC get a
// self-signed certificate; KEM keys get their public key PEM, as the
// platform's service/cmd/keygen writes it.
func keygen(alg string) (keyMaterial, error) {
	kt, err := ocrypto.ParseKeyType(alg)
	if err != nil {
		return keyMaterial{}, err
	}
	kp, err := ocrypto.NewKeyPair(kt)
	if err != nil {
		return keyMaterial{}, err
	}
	priv, err := kp.PrivateKeyInPemFormat()
	if err != nil {
		return keyMaterial{}, err
	}
	var cert string
	if ocrypto.IsRSAKeyType(kt) || ocrypto.IsECKeyType(kt) {
		cert, err = selfSignedCert(priv)
	} else {
		cert, err = kp.PublicKeyInPemFormat()
	}
	if err != nil {
		return keyMaterial{}, err
	}
	return keyMaterial{Alg: alg, PrivateKey: priv, Cert: cert}, nil
}

func selfSignedCert(privPEM string) (string, error) {
	signer, err := parseSigner(privPEM)
	if err != nil {
		return "", err
	}
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 127))
	if err != nil {
		return "", err
	}
	now := time.Now().UTC().Truncate(time.Second)
	tmpl := &x509.Certificate{
		SerialNumber:          serial,
		Subject:               pkix.Name{CommonName: "corpus"},
		NotBefore:             now,
		NotAfter:              now.AddDate(10, 0, 0),
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, signer.Public(), signer)
	if err != nil {
		return "", err
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})), nil
}

func parseSigner(privPEM string) (crypto.Signer, error) {
	block, _ := pem.Decode([]byte(privPEM))
	if block == nil {
		return nil, errors.New("no PEM block in private key")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	signer, ok := key.(crypto.Signer)
	if !ok {
		return nil, fmt.Errorf("unsupported private key type %T", key)
	}
	return signer, nil
}

// publicPEM returns the SubjectPublicKeyInfo PEM for a private key PEM.
func publicPEM(privPEM string) (string, error) {
	dec, err := ocrypto.FromPrivatePEM(privPEM)
	if err != nil {
		return "", err
	}
	if kt, ok := kemKeyType(dec); ok {
		return kemPublicPEM(privPEM, kt)
	}
	signer, err := parseSigner(privPEM)
	if err != nil {
		return "", err
	}
	der, err := x509.MarshalPKIXPublicKey(signer.Public())
	if err != nil {
		return "", err
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})), nil
}

func kemKeyType(dec ocrypto.PrivateKeyDecryptor) (ocrypto.KeyType, bool) {
	k, ok := dec.(interface{ KeyType() ocrypto.KeyType })
	if !ok {
		return "", false
	}
	return k.KeyType(), true
}

// ocrypto writes a KEM key's PKCS#8 and SPKI envelopes with the same
// AlgorithmIdentifier, so the public envelope reuses the private one's.
type pkcs8Envelope struct {
	Version    int
	Algorithm  asn1.RawValue
	PrivateKey []byte
}

type spkiEnvelope struct {
	Algorithm asn1.RawValue
	PublicKey asn1.BitString
}

func kemPublicPEM(privPEM string, kt ocrypto.KeyType) (string, error) {
	block, _ := pem.Decode([]byte(privPEM))
	if block == nil {
		return "", errors.New("no PEM block in private key")
	}
	var env pkcs8Envelope
	if rest, err := asn1.Unmarshal(block.Bytes, &env); err != nil {
		return "", fmt.Errorf("parse %s PKCS#8: %w", kt, err)
	} else if len(rest) > 0 {
		return "", fmt.Errorf("parse %s PKCS#8: %d trailing bytes", kt, len(rest))
	}
	raw, err := kemPublicKey(kt, env.PrivateKey)
	if err != nil {
		return "", err
	}
	der, err := asn1.Marshal(spkiEnvelope{
		Algorithm: env.Algorithm,
		PublicKey: asn1.BitString{Bytes: raw, BitLength: 8 * len(raw)},
	})
	if err != nil {
		return "", err
	}
	pub := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
	enc, err := ocrypto.FromPublicPEM(pub)
	if err != nil {
		return "", fmt.Errorf("derived %s public key: %w", kt, err)
	}
	if enc.KeyType() != kt {
		return "", fmt.Errorf("derived public key is %s, want %s", enc.KeyType(), kt)
	}
	return pub, nil
}

func kemPublicKey(kt ocrypto.KeyType, priv []byte) ([]byte, error) {
	switch kt {
	case ocrypto.MLKEM768Key, ocrypto.MLKEM1024Key:
		// The seed sits in a [0] IMPLICIT OCTET STRING (RFC 5958 KEM CHOICE).
		var seed []byte
		if rest, err := asn1.UnmarshalWithParams(priv, &seed, "tag:0,implicit"); err != nil {
			return nil, fmt.Errorf("parse %s seed: %w", kt, err)
		} else if len(rest) > 0 {
			return nil, fmt.Errorf("parse %s seed: %d trailing bytes", kt, len(rest))
		}
		return mlkemPublicKey(kt == ocrypto.MLKEM1024Key, seed)
	case ocrypto.HybridXWingKey:
		if len(priv) != xwing.SeedSize {
			return nil, fmt.Errorf("X-Wing private key is %d bytes, want %d", len(priv), xwing.SeedSize)
		}
		_, pub := xwing.DeriveKeyPairPacked(priv)
		return pub, nil
	case ocrypto.HybridSecp256r1MLKEM768Key, ocrypto.HybridSecp384r1MLKEM1024Key:
		if len(priv) <= mlkemSeedSize {
			return nil, fmt.Errorf("%s private key too short", kt)
		}
		mlkemPub, err := mlkemPublicKey(kt == ocrypto.HybridSecp384r1MLKEM1024Key, priv[:mlkemSeedSize])
		if err != nil {
			return nil, err
		}
		ecPriv, err := x509.ParseECPrivateKey(priv[mlkemSeedSize:])
		if err != nil {
			return nil, err
		}
		ecdhPriv, err := ecPriv.ECDH()
		if err != nil {
			return nil, err
		}
		return append(mlkemPub, ecdhPriv.PublicKey().Bytes()...), nil
	default:
		return nil, fmt.Errorf("unsupported KEM key type %s", kt)
	}
}

func mlkemPublicKey(is1024 bool, seed []byte) ([]byte, error) {
	if is1024 {
		dk, err := mlkem.NewDecapsulationKey1024(seed)
		if err != nil {
			return nil, err
		}
		return dk.EncapsulationKey().Bytes(), nil
	}
	dk, err := mlkem.NewDecapsulationKey768(seed)
	if err != nil {
		return nil, err
	}
	return dk.EncapsulationKey().Bytes(), nil
}

// unwrap returns the key share in one KAO, decrypted as the KAS rewrap does
// (service/kas/access/rewrap.go, service/internal/security/standard_crypto.go).
func unwrap(privPEM string, kaoJSON []byte) ([]byte, error) {
	var kao keyAccess
	if err := json.Unmarshal(kaoJSON, &kao); err != nil {
		return nil, fmt.Errorf("parse KAO: %w", err)
	}
	key, err := unwrapKAO(privPEM, kao)
	if err != nil {
		return nil, fmt.Errorf("KAO type %q: %w", kao.Type, err)
	}
	return key, nil
}

func unwrapKAO(privPEM string, kao keyAccess) ([]byte, error) {
	var decrypt func([]byte) ([]byte, error)
	var err error
	switch kao.Type {
	case kaoWrapped:
		decrypt, err = rsaDecrypt(privPEM)
	case kaoECWrapped:
		decrypt, err = ecDecrypt(privPEM, kao.EphemeralPublicKey)
	case kaoHybridWrapped:
		decrypt, err = kemDecrypt(privPEM, ocrypto.IsHybridKeyType)
	case kaoMLKEMWrapped:
		decrypt, err = kemDecrypt(privPEM, ocrypto.IsMLKEMKeyType)
	default:
		return nil, errors.New("unsupported KAO type")
	}
	if err != nil {
		return nil, err
	}
	wrapped, err := ocrypto.Base64Decode([]byte(kao.WrappedKey))
	if err != nil {
		return nil, fmt.Errorf("wrappedKey: %w", err)
	}
	if len(wrapped) == 0 {
		return nil, errors.New("wrappedKey is empty")
	}
	return decrypt(wrapped)
}

func rsaDecrypt(privPEM string) (func([]byte) ([]byte, error), error) {
	dec, err := ocrypto.FromPrivatePEM(privPEM)
	if err != nil {
		return nil, err
	}
	rsaDec, ok := dec.(ocrypto.AsymDecryption)
	if !ok {
		return nil, errors.New("private key is not RSA")
	}
	return rsaDec.Decrypt, nil
}

func ecDecrypt(privPEM, ephemeralPEM string) (func([]byte) ([]byte, error), error) {
	ephemeral, err := compressedEphemeralKey(ephemeralPEM)
	if err != nil {
		return nil, err
	}
	dec, err := ocrypto.FromPrivatePEMWithSalt(privPEM, tdfSalt(), nil)
	if err != nil {
		return nil, err
	}
	ecDec, ok := dec.(ocrypto.ECDecryptor)
	if !ok {
		return nil, errors.New("private key is not EC")
	}
	return func(wrapped []byte) ([]byte, error) {
		return ecDec.DecryptWithEphemeralKey(wrapped, ephemeral)
	}, nil
}

func kemDecrypt(privPEM string, isFamily func(ocrypto.KeyType) bool) (func([]byte) ([]byte, error), error) {
	dec, err := ocrypto.FromPrivatePEM(privPEM)
	if err != nil {
		return nil, err
	}
	kt, ok := kemKeyType(dec)
	if !ok {
		return nil, errors.New("private key is not a KEM key")
	}
	if !isFamily(kt) {
		return nil, fmt.Errorf("private key is %s, which this KAO type does not use", kt)
	}
	return dec.Decrypt, nil
}

// compressedEphemeralKey turns the KAO's PEM ephemeral key into the
// compressed point the KAS hands its EC decryptor.
func compressedEphemeralKey(ephemeralPEM string) ([]byte, error) {
	size, err := ocrypto.GetECKeySize([]byte(ephemeralPEM))
	if err != nil {
		return nil, fmt.Errorf("ephemeralPublicKey: %w", err)
	}
	mode, err := ocrypto.ECSizeToMode(size)
	if err != nil {
		return nil, fmt.Errorf("ephemeralPublicKey: %w", err)
	}
	block, _ := pem.Decode([]byte(ephemeralPEM))
	if block == nil {
		return nil, errors.New("ephemeralPublicKey: no PEM block")
	}
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("ephemeralPublicKey: %w", err)
	}
	ecPub, ok := pub.(*ecdsa.PublicKey)
	if !ok {
		return nil, errors.New("ephemeralPublicKey is not EC")
	}
	return ocrypto.CompressedECPublicKey(mode, *ecPub)
}

// tdfSalt is the HKDF salt the SDK uses for ec-wrapped KAOs (sdk/tdf.go).
func tdfSalt() []byte {
	salt := sha256.Sum256([]byte("TDF"))
	return salt[:]
}
