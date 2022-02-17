# Deployments

This folder contains deployment-specific scripts and Helm chart values overrides for deploying in different contexts,
where that is necessary. Currently, this is only required for local deployments.

Should it become necessary to add a new kind of deployment (expressed as Helm chart values.yaml overrides, scripts, etc),
create a new folder in here to avoid polluting the repo root.
