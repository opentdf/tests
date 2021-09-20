# Parent chart

## Develop

### Helm chart

Import sub-charts
```shell
helm dependency update charts/etheria
```

To test changes in sub-charts from parent chart
```shell
rm charts/etheria/Chart.lock
rm -rf charts/etheria/charts
helm dependency update charts/etheria 
```

To view flat, transformed manifest
```shell
# eks
helm template etheria charts/etheria \
  --debug \
  --values deployments/eks/values-keycloak-tdf.yaml

# local (e.g. minikube or kind)
helm template etheria charts/etheria \
  --debug \
  --values deployments/local/values-all-in-one.yaml


```

To upgrade
```shell
helm upgrade --install --namespace tdf etheria charts/etheria \
  --values deployments/eks/values-keycloak-tdf.yaml
```
