package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"encoding/json"
	"strings"
)

// PolicyClient wraps otdfctl functionality
// Initially using subprocess calls, but can be refactored to use direct SDK calls
type PolicyClient struct {
	endpoint string
	otdfctl  string
}

func NewPolicyClient(endpoint string) (*PolicyClient, error) {
	// Find otdfctl binary - check multiple locations
	possiblePaths := []string{
		"../sdk/go/otdfctl.sh",
		"../sdk/go/dist/main/otdfctl.sh",
		"../../xtest/sdk/go/otdfctl.sh",
		"../../xtest/sdk/go/dist/main/otdfctl.sh",
		"xtest/sdk/go/otdfctl.sh",
		"xtest/sdk/go/dist/main/otdfctl.sh",
	}
	
	var otdfctl string
	for _, path := range possiblePaths {
		if _, err := os.Stat(path); err == nil {
			otdfctl = path
			break
		}
	}
	
	if otdfctl == "" {
		return nil, fmt.Errorf("otdfctl.sh not found in any expected location")
	}

	return &PolicyClient{
		endpoint: endpoint,
		otdfctl:  otdfctl,
	}, nil
}

// execCommand runs an otdfctl command and returns the output
func (c *PolicyClient) execCommand(args ...string) ([]byte, error) {
	cmd := exec.Command(c.otdfctl, args...)
	output, err := cmd.Output()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return nil, fmt.Errorf("command failed: %s", string(exitErr.Stderr))
		}
		return nil, err
	}
	return output, nil
}

// KAS Registry operations

func (c *PolicyClient) ListKasRegistries(ctx context.Context) ([]map[string]interface{}, error) {
	output, err := c.execCommand("policy", "kas-registry", "list")
	if err != nil {
		return nil, err
	}

	var result []map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) CreateKasRegistry(ctx context.Context, uri string, publicKeys string) (map[string]interface{}, error) {
	args := []string{"policy", "kas-registry", "create", fmt.Sprintf("--uri=%s", uri)}
	if publicKeys != "" {
		args = append(args, fmt.Sprintf("--public-keys=%s", publicKeys))
	}

	output, err := c.execCommand(args...)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) ListKasRegistryKeys(ctx context.Context, kasURI string) ([]map[string]interface{}, error) {
	output, err := c.execCommand("policy", "kas-registry", "key", "list", fmt.Sprintf("--kas=%s", kasURI))
	if err != nil {
		return nil, err
	}

	var result []map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) CreateKasRegistryKey(ctx context.Context, kasURI, publicKeyPEM, keyID, algorithm string) (map[string]interface{}, error) {
	args := []string{
		"policy", "kas-registry", "key", "create",
		"--mode", "public_key",
		fmt.Sprintf("--kas=%s", kasURI),
		fmt.Sprintf("--public-key-pem=%s", publicKeyPEM),
		fmt.Sprintf("--key-id=%s", keyID),
		fmt.Sprintf("--algorithm=%s", algorithm),
	}

	output, err := c.execCommand(args...)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// Namespace operations

func (c *PolicyClient) ListNamespaces(ctx context.Context) ([]map[string]interface{}, error) {
	output, err := c.execCommand("policy", "attributes", "namespaces", "list")
	if err != nil {
		return nil, err
	}

	var result []map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) CreateNamespace(ctx context.Context, name string) (map[string]interface{}, error) {
	output, err := c.execCommand("policy", "attributes", "namespaces", "create", fmt.Sprintf("--name=%s", name))
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// Attribute operations

func (c *PolicyClient) CreateAttribute(ctx context.Context, namespaceID, name, rule string, values []string) (map[string]interface{}, error) {
	args := []string{
		"policy", "attributes", "create",
		fmt.Sprintf("--namespace=%s", namespaceID),
		fmt.Sprintf("--name=%s", name),
		fmt.Sprintf("--rule=%s", rule),
	}
	if len(values) > 0 {
		args = append(args, fmt.Sprintf("--value=%s", strings.Join(values, ",")))
	}

	output, err := c.execCommand(args...)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// Key assignment operations

func (c *PolicyClient) AssignNamespaceKey(ctx context.Context, keyID, namespaceID string) (map[string]interface{}, error) {
	output, err := c.execCommand(
		"policy", "attributes", "namespace", "key", "assign",
		fmt.Sprintf("--key-id=%s", keyID),
		fmt.Sprintf("--namespace=%s", namespaceID),
	)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) AssignAttributeKey(ctx context.Context, keyID, attributeID string) (map[string]interface{}, error) {
	output, err := c.execCommand(
		"policy", "attributes", "key", "assign",
		fmt.Sprintf("--key-id=%s", keyID),
		fmt.Sprintf("--attribute=%s", attributeID),
	)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) AssignValueKey(ctx context.Context, keyID, valueID string) (map[string]interface{}, error) {
	output, err := c.execCommand(
		"policy", "attributes", "value", "key", "assign",
		fmt.Sprintf("--key-id=%s", keyID),
		fmt.Sprintf("--value=%s", valueID),
	)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) UnassignNamespaceKey(ctx context.Context, keyID, namespaceID string) (map[string]interface{}, error) {
	output, err := c.execCommand(
		"policy", "attributes", "namespace", "key", "unassign",
		fmt.Sprintf("--key-id=%s", keyID),
		fmt.Sprintf("--namespace=%s", namespaceID),
	)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) UnassignAttributeKey(ctx context.Context, keyID, attributeID string) (map[string]interface{}, error) {
	output, err := c.execCommand(
		"policy", "attributes", "key", "unassign",
		fmt.Sprintf("--key-id=%s", keyID),
		fmt.Sprintf("--attribute=%s", attributeID),
	)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) UnassignValueKey(ctx context.Context, keyID, valueID string) (map[string]interface{}, error) {
	output, err := c.execCommand(
		"policy", "attributes", "value", "key", "unassign",
		fmt.Sprintf("--key-id=%s", keyID),
		fmt.Sprintf("--value=%s", valueID),
	)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// Subject Condition Set operations

func (c *PolicyClient) CreateSubjectConditionSet(ctx context.Context, subjectSets string) (map[string]interface{}, error) {
	output, err := c.execCommand(
		"policy", "subject-condition-sets", "create",
		fmt.Sprintf("--subject-sets=%s", subjectSets),
	)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *PolicyClient) CreateSubjectMapping(ctx context.Context, attributeValueID, subjectConditionSetID, action string) (map[string]interface{}, error) {
	// Try with --action first, fall back to --action-standard if needed
	args := []string{
		"policy", "subject-mappings", "create",
		fmt.Sprintf("--attribute-value-id=%s", attributeValueID),
		fmt.Sprintf("--subject-condition-set-id=%s", subjectConditionSetID),
		fmt.Sprintf("--action=%s", action),
	}

	output, err := c.execCommand(args...)
	if err != nil {
		// Try with --action-standard flag for older versions
		if strings.Contains(err.Error(), "--action-standard") {
			args[len(args)-1] = fmt.Sprintf("--action-standard=%s", action)
			output, err = c.execCommand(args...)
			if err != nil {
				return nil, err
			}
		} else {
			return nil, err
		}
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, err
	}
	return result, nil
}