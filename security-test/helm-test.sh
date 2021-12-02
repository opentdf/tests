

helm repo add secureCodeBox https://charts.securecodebox.io

# Create a new namespace for the secureCodeBox Operator
kubectl create namespace securecodebox-system

# Install the Operator & CRD's
helm --namespace securecodebox-system upgrade --install securecodebox-operator --version 3.1.1 secureCodeBox/operator


helm upgrade --install zap-advanced secureCodeBox/zap-advanced

for service in attributes:4020 entitlements:4030 key-access:8000; do
  service_name=${service%:*}
  cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: zap-advanced-scan-config-${service_name}
data:
  2-zap-advanced-scan-${service_name}.yaml: |-
    contexts:
      - name: scb-context-${service_name}
        url: http://opentdf-${service}/
    apis:
      - name: scb-api-${service_name}
        context: scb-context-${service_name}
        format: openapi
        url: http://opentdf-${service}/openapi.json
---
apiVersion: "execution.securecodebox.io/v1"
kind: Scan
metadata:
  name: "zap-scan-${service_name}"
  labels:
    organization: "OWASP"
spec:
  scanType: "zap-advanced-scan"
  parameters:
    - "-t"
    - "http://opentdf-${service}/"
    - "-r"
    - "HTML"
  volumeMounts:
    - name: zap-advanced-scan-config-${service_name}
      mountPath: /home/securecodebox/configs/2-zap-advanced-scan-${service_name}.yaml
      subPath: 2-zap-advanced-scan-${service_name}.yaml
      readOnly: true
  volumes:
    - name: zap-advanced-scan-config-${service_name}
      configMap:
        name: zap-advanced-scan-config-${service_name}
EOF
done

kubectl get scans

echo "Check the logs in the jobs' pods for updates."
echo "For output, look in the minio service. See: https://docs.securecodebox.io/docs/getting-started/installation#accessing-the-included-minio-instance"
