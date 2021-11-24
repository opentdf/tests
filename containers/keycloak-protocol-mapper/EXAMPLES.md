# Keycloak flow examples

### Token Exchange flow example

Keycloak and the OIDC protocol support exchanging OIDC tokens with other trusted IdPs (Google, Azure, etc)
- [Docs](https://github.com/keycloak/keycloak-documentation/blob/master/securing_apps/topics/token-exchange/token-exchange.adoc) - See External [External Token to Internal Token Exchange](https://github.com/keycloak/keycloak-documentation/blob/master/securing_apps/topics/token-exchange/token-exchange.adoc#external-token-to-internal-token-exchange)
- [token exchange example](https://www.mathieupassenaud.fr/token-exchange-keycloak/)

Example:
- assumes 'test' keycloak client
- uses keycloak-poc google project within the virtrudemos.com account.

1. Enable token-exchange feature (This is enabled by default with the previous container run configuration)
    - -Dkeycloak.profile=preview
    -  -Dkeycloak.profile.feature.token_exchange=enabled
2. Add a google identity provider to keycloak
    1. Identity Providers > Add Providers > Google
    2. Enter Client ID and secret values pulled from [Client ID for Web Client](https://console.cloud.google.com/apis/credentials/oauthclient/317460954727-l5nojaai8iru4esbvurqjt1emb91fkea.apps.googleusercontent.com?authuser=2&project=keycloak-poc-305618) logged in as admin@virtrudemos.com
3. Update token exchange permissions. Under "Permissions" tab of the newly created google identity provider click the token-exchange permission.
    1. Create a policy = Create Policy > Client > set client id > Save.
   
    ![Google IDP Token Exchage Policy](./readme-images/ehpolicy.png?raw=true)

    2. Verify new client policy is displayed   
    
    ![Google IDP Token Exchage Policy](./readme-images/google_idp_wexhpolicy.png?raw=true)
4. Add token exchange permission to keycloak client
    1. Goto token exchange permission 
    
    ![Client Token Exchage Permission](./readme-images/client_permissions.png?raw=true)

    2. Add the policy from previous step
    
    ![Client IDP Token Exchage Policy](./readme-images/client_expolicy.png?raw=true)
5. Auth to Google and copy access token: - [google oauth2 playground](https://developers.google.com/oauthplayground/)
                    
6. Try it out
    
    params:
    - client_id = keycloak client id
    - client_secret = keycloak client secret
    - grant_type = the token exhange grant type: urn:ietf:params:oauth:grant-type:token-exchange
    - subject_token =  the access token from a successful google authentication (previous step)
    - subject_issuer
    - subject_token_type = urn:ietf:params:oauth:token-type:access_token
    - audience: keycloak client id
    ```
    curl --request POST \
      --url http://localhost:8080/auth/realms/master/protocol/openid-connect/token \
      --header 'content-type: application/x-www-form-urlencoded' \
      --data 'client_id=test&client_secret=$CLIENT_SECRET&grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&subject_token=$SUBJECT_TOKEN&subject_issuer=google&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&audience=test'
    ```     


### Identity Broker

Keycloak supports brokering authentication by querying an external/remote IdP during the auth process.

example using google:

Add new "google" identity broker to keycloak.  use the client id and client secret present in the "keycloak-poc" project under
the virtrudemos.com organization.

[google devloper console](https://console.developers.google.com/)
- account: virtrudemos.com (1password contains login creds)
- project=keycloak-poc
- [google dev console direct link to oauth client](https://console.cloud.google.com/apis/credentials/oauthclient/317460954727-l5nojaai8iru4esbvurqjt1emb91fkea.apps.googleusercontent.com?authuser=2&project=keycloak-poc-305618)

## Steps To Demonstrate Custom Claim Via Manual Testing

* Log into the Keycloak admin console.
* Hover over the realm name at the top left of the browser window and click "Add Realm".
  - Name:  `example-realm`
  - Display Name:  `example-realm`
  - Click `Save`
* Select the newly created realm by clicking it at the top left.
* Click `Clients` on the left menu bar.  Click the `Create` button.
  - Client ID:  `example-realm-client`
  - Name:  `example-realm-client`
  - Valid Redirect URIs:  `http://127.0.0.1:5000`
    - I don't think this matters for our test, so don't worry if it's bad/wrong.
  - Click `Save`
* Click `Clients` at the left menu bar and then `example-realm-client`.
  - Click the `Mappers` tab.  Click the `Create` button.
  - Name:  `whatever you want`
  - Mapper Type:  `de bes`  # because before said `ohhhhh noooooo`
  - Token Claim Name:  `claim.name`
  - Send User Name:  `on`
  - URL:  `http://<ip address of en0>:5000`
    - Look at `$ ifconfig` and find the ip address for `en0` and use that.
  - Click `Save`.
* Click `Users` in the left menu bar back at the admin console.  Click the `Create` button.
  - Username:  `whatever-you-want`.
  - Click `Save`
  - On the newly created user's detail screen, click the `Credentials` tab.
  - Password:  `password`
  - Confirm Password:  `password`
  - Temporary Password:  `OFF`
  - Click `Set Password`

* Start the Keycloak container with the custom protocol mapper:

```
docker run -p 8080:8080 \
  -e KEYCLOAK_USER=admin \
  -e KEYCLOAK_PASSWORD=admin \
  virtru/tdf-keycloak:0.0.2
```

* `cd` to `custom-claim-test-webservice` and follow the directions in `README.md`
  to do setup (if necessary) and start the web service.  Make sure it's running on `0.0.0.0:5000`
  so that Keycloak can reach it.

```
(venv) jgrady@jgrady custom-claim-test-webservice % ./run.sh
 * Serving Flask app "app.py" (lazy loading)
 * Environment: development
 * Debug mode: on
 * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 176-043-272
 ...
```

* Run the following command in a terminal, substituting your newly created username for `jeff5-example`:

```
$ curl -d 'client_id=example-realm-client' \
       -d 'username=jeff5-example' \
       -d 'password=password' \
       -d 'grant_type=password' \
       'http://localhost:8080/auth/realms/example-realm/protocol/openid-connect/token'
```

If it works, you should see something that looks like this:

```
jgrady@jgrady git % curl -d 'client_id=example-realm-client' -d 'username=jeff5-example' -d 'password=password' -d 'grant_type=password' 'http://localhost:8080/auth/realms/example-realm/protocol/openid-connect/token'

{"access_token":"eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJGRjJKM0o5TjNGQWQ0dnpLVDd2aEloZE1DTEVudE1PejVtLWhGNm5ScFNZIn0.eyJleHAiOjE2MTQxMTgzNzgsImlhdCI6MTYxNDExODA3OCwianRpIjoiNWQ4OTczYjYtYjg5Yy00OTBjLWIzYTYtMTM0ZDMxOTYxZTM3IiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL2V4YW1wbGUtcmVhbG0iLCJhdWQiOiJhY2NvdW50Iiwic3ViIjoiN2ZkZGJkYWQtNDlmYS00NWU4LTg4MzItMzI3ZGI4ZjU1MDE1IiwidHlwIjoiQmVhcmVyIiwiYXpwIjoiZXhhbXBsZS1yZWFsbS1jbGllbnQiLCJzZXNzaW9uX3N0YXRlIjoiOTA0MTc4NTAtNWEwNC00ZmU1LTgxZWMtOTkzZDY1MmVhYmY5IiwiYWNyIjoiMSIsInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJwcm9maWxlIGVtYWlsIiwic3VwaXJpIjoidG9rZW5fc3VwaXJpIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJjbGFpbSI6eyJuYW1lIjp7InVzZXJuYW1lIjoiZm9vIn19LCJwcmVmZXJyZWRfdXNlcm5hbWUiOiJqZWZmNS1leGFtcGxlIn0.NfM272HpLfyHACNJrXniyPF5klXjfB8QbhHBt_aTlZUF1-wO7W4-3qL02bMYe71dg_swR5WLFR0SL-zqa9zeKfsegL8E-lEeRSCcFwTvoSXPXSZ06tafFmSNxuA88MogG_3ZBhi9sUL5uAXtCoC3Rkb6xpb-JdHp42n68s_Mm1teCU2wx2rS6O1k23YCK3lY_xRsmV62sQ_tx973N5u7YHPxWsKVi-gHNlW3N0x23bRsEk-qcIq-3ug5cLOyADlNUeApTmug9lXGJxqxo3jlugnuf6VUtMwI1x8xSbePwC1pmGAfzZX2pS0kEUiGSHdH7flzibrMG70IXlutmS3e8Q","expires_in":300,"refresh_expires_in":1800,"refresh_token":"eyJhbGciOiJIUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICI3ODI5MjQ0My1iMWFmLTRiMzAtOTUwYy1iNWQwZGQ4OWZhMWMifQ.eyJleHAiOjE2MTQxMTk4NzgsImlhdCI6MTYxNDExODA3OCwianRpIjoiNWRlNDUyZjAtNmQwOS00ZmZjLTkyZjEtNDJiOTRjM2RmM2Q3IiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL2V4YW1wbGUtcmVhbG0iLCJhdWQiOiJodHRwOi8vbG9jYWxob3N0OjgwODAvYXV0aC9yZWFsbXMvZXhhbXBsZS1yZWFsbSIsInN1YiI6IjdmZGRiZGFkLTQ5ZmEtNDVlOC04ODMyLTMyN2RiOGY1NTAxNSIsInR5cCI6IlJlZnJlc2giLCJhenAiOiJleGFtcGxlLXJlYWxtLWNsaWVudCIsInNlc3Npb25fc3RhdGUiOiI5MDQxNzg1MC01YTA0LTRmZTUtODFlYy05OTNkNjUyZWFiZjkiLCJzY29wZSI6InByb2ZpbGUgZW1haWwifQ.RH4xGiPL0hC6ArTTBxOxnRQkASbGYHnIExGV3qBDOpI","token_type":"Bearer","not-before-policy":0,"session_state":"90417850-5a04-4fe5-81ec-993d652eabf9","scope":"profile email"}%
```

Examine the token however you like.  Here's a Python example.

If you want to try it, the python venv for our example web service comes installed with `pyjwt` which should work as below:

```
(venv) jgrady@jgrady custom-claim-test-webservice % python
Python 3.7.3 (default, Apr 24 2020, 18:51:23)
[Clang 11.0.3 (clang-1103.0.32.62)] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> import jwt
>>> jeff = """eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJGRjJKM0o5TjNGQWQ0dnpLVDd2aEloZE1DTEVudE1PejVtLWhGNm5ScFNZIn0.eyJleHAiOjE2MTQxMTc0MzIsImlhdCI6MTYxNDExNzEzMiwianRpIjoiZjRjZTE2NjMtM2QwZC00OWRjLThjMDgtNzI5YjU2MWFiNzQ5IiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL2V4YW1wbGUtcmVhbG0iLCJhdWQiOiJhY2NvdW50Iiwic3ViIjoiZmU5NTFhNTMtZTMwYy00ZDQ2LTlmYjQtNWNmMjcwZDlhZGM1IiwidHlwIjoiQmVhcmVyIiwiYXpwIjoiZXhhbXBsZS1yZWFsbS1jbGllbnQiLCJzZXNzaW9uX3N0YXRlIjoiOTQyYTU1ZGYtNmFjZS00ZjM3LTk1NjQtMGE0MzZiZmMwNDY0IiwiYWNyIjoiMSIsInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJwcm9maWxlIGVtYWlsIiwic3VwaXJpIjoidG9rZW5fc3VwaXJpIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJjbGFpbSI6eyJuYW1lIjp7InVzZXJuYW1lIjoiZm9vIn19LCJwcmVmZXJyZWRfdXNlcm5hbWUiOiJqZWZmLWV4YW1wbGUifQ.QzB8-D_zSENh32d10VDZ8j2VMo0AXMqZTk55CPG40cE1ROuAz4c4IbtVZvblXQBaD8H1xJPUIphi0uUk0sTmVwchstME7CPZsuOJDvAgbAahwkdNjMTbPbVyQpBadoXbMbwHxqZvMKwkf06yrzcJbT--AVoSDk-_yDOxW_i_KTTmtkia4yFf_RhAzQPycDIjXrKS_rnja-WvNAVCOY6qrIMIci-fdEpDQLdtYcPJFW0DECwTUiZ07A2k7pi21ROCdrxygLZ91Jk8JXnsooesgWF26aNAnrEzntuZynUe3D_VefbtU6-PYXex29qyxykD54LNw76OiFXZxaSbiUrFVQ"""
>>> jeff_decoded = jwt.decode(jeff, options={"verify_signature": False})
>>> from pprint import pprint
>>> pprint(jeff_decoded)
{'acr': '1',
 'aud': 'account',
 'azp': 'example-realm-client',
 'claim': {'name': {'username': 'foo'}},
 'email_verified': False,
 'exp': 1614117432,
 'iat': 1614117132,
 'iss': 'http://localhost:8080/auth/realms/example-realm',
 'jti': 'f4ce1663-3d0d-49dc-8c08-729b561ab749',
 'preferred_username': 'jeff-example',
 'realm_access': {'roles': ['offline_access', 'uma_authorization']},
 'resource_access': {'account': {'roles': ['manage-account',
                                           'manage-account-links',
                                           'view-profile']}},
 'scope': 'profile email',
 'session_state': '942a55df-6ace-4f37-9564-0a436bfc0464',
 'sub': 'fe951a53-e30c-4d46-9fb4-5cf270d9adc5',
 'supiri': 'token_supiri',
 'typ': 'Bearer'}
```

Notice the line `'claim': {'name': {'username': 'foo'}},` that came from our web service.  :+1:

### Fetching signed JWT claims from `/userinfo` endpoint

#### Generate bearer auth token (lacks TDF claims)
curl --location --request POST 'http://localhost:8080/auth/realms/tdf/protocol/openid-connect/token' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data-urlencode 'grant_type=password' \
--data-urlencode 'client_id=tdf-client' \
--data-urlencode 'client_secret=123-456' \
--data-urlencode 'username=user1' \
--data-urlencode 'password=password'

#### Fetch userinfo claims token (has TDF claims, signed by KC)
curl --location --request POST 'http://localhost:8080/auth/realms/tdf/protocol/openid-connect/userinfo' \
--header 'X-VirtruPubkey: EEEE' \
--header 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJETXlyN0M5RUg2OTI2X0RHODZVTTh6aC1UUEZkZ1paRHRPOVdWTk9PM0....


Response will be a signed JWT with Virtru claims
