# Client Cross-Test

Work In Progress

(Currently only tests checked-in )

## Usage:

```
( cd tests/integration && tilt up & )
docker build --tag opentdf/xtest --file tetss/containers/clients/Dockerfile .
docker run opentdf/xtest
```

### Expected output:

```
INFO:xtest:--- main
INFO:xtest:--- run_cli_tests {<function encrypt_web at 0xffff943bc1e0>} => {<function decrypt_web at 0xffff93c87d08>}
INFO:xtest:--- Begin Test #0: Roundtrip encrypt(<function encrypt_web at 0xffff943bc1e0>) --> decrypt(<function decrypt_web at 0xffff93c87d08>)
INFO:xtest:Encrypt <function encrypt_web at 0xffff943bc1e0>
INFO:xtest:Invoking subprocess: npx @opentdf/cli --kasEndpoint http://host.docker.internal:65432/kas --oidcEndpoint http://host.docker.internal:65432/keycloak --auth tdf:tdf-client:123-456 --output tmp/test-0.tdf encrypt tmp/test-plain-small.txt
This policy has an empty attributes list and an empty dissemination list. This will allow any entity with a valid Entity Object to access this TDF.
{ jwsAlg: 'ECDH-ES', subtleAlg: { name: 'ECDH', namedCurve: 'P-256' } }
INFO:xtest:Decrypt <function decrypt_web at 0xffff93c87d08>
INFO:xtest:Invoking subprocess: npx @opentdf/cli --kasEndpoint http://host.docker.internal:65432/kas --oidcEndpoint http://host.docker.internal:65432/keycloak --auth tdf:tdf-client:123-456 --output tmp/test-0.untdf decrypt tmp/test-0.tdf
INFO:xtest:Test #0, (<function encrypt_web at 0xffff943bc1e0>-><function decrypt_web at 0xffff93c87d08>): Succeeded!
INFO:xtest:All tests succeeded!
```