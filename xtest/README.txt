# x-test

> Compatibility tests for opentdf client libraries and tools.

Requirements:

- go 1.22.3
- node 20
- python 3.10
- jdk 11

## Bringing up the platform backend (macOS)

1. checkout platform (`git checkout https://github.com/opentdf/platform`)
2. switch to the the platform folder (`cd platform`)
3. configure and initialize the platform ()
   a. `cp opentdf-dev.yaml opentdf.yaml` & edit the yaml if needed
   b. `.github/scripts/init-temp-keys.sh`
   c. `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ./keys/localhost.crt`
      i. To remove, `sudo security delete-certificate -c "localhost"`
4. Bring up background services, `docker compose up`
5. Add sample users and realm to keycloak, `go run ./service provision keycloak`
6. Add sample attributes and metadata, `go run ./service provision fixtures`
7. start server in background, `go run ./service start`

## Testing with Released Software

