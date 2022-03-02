package com.virtru.keycloak;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.client.utils.URIBuilder;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClientBuilder;
import org.apache.http.util.EntityUtils;
import org.jboss.resteasy.plugins.providers.RegisterBuiltin;
import org.jboss.resteasy.plugins.providers.jackson.ResteasyJackson2Provider;
import com.fasterxml.jackson.core.JsonProcessingException;
import org.jboss.resteasy.spi.ResteasyProviderFactory;
import org.keycloak.models.*;
import org.keycloak.protocol.oidc.mappers.*;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.IDToken;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.util.*;
import java.util.stream.Collectors;
import java.util.Map;

/**
 * Custom OIDC Protocol Mapper that interfaces with an Attribute Provider Endpoint to retrieve custom claims to be
 * placed in a configured custom claim name
 *
 * - Configurable properties allow for providing additional header and proprty values to be passed to the attribute provider.
 *
 */
public class AttributeOIDCProtocolMapper extends AbstractOIDCProtocolMapper implements OIDCAccessTokenMapper, OIDCIDTokenMapper, UserInfoTokenMapper {

    public static final String PROVIDER_ID = "virtru-oidc-protocolmapper";

    private static final List<ProviderConfigProperty> configProperties = new ArrayList<ProviderConfigProperty>();

    final static String REMOTE_URL = "remote.url";
    final static String REMOTE_HEADERS = "remote.headers";
    final static String REMOTE_PARAMETERS = "remote.parameters";
    final static String REMOTE_PARAMETERS_USERNAME = "remote.parameters.username";
    final static String REMOTE_PARAMETERS_CLIENTID = "remote.parameters.clientid";
    final static String CLAIM_NAME = "claim.name";
    final static String PUBLIC_KEY_HEADER = "client.publickey";
    final static String CLAIM_REQUEST_TYPE = "claim_request_type";

    private CloseableHttpClient client = HttpClientBuilder.create().build();

    private Logger logger = LoggerFactory.getLogger(getClass());

    /**
     * Inner configuration to cache retrieved authorization for multiple tokens
     */
    private final static String REMOTE_AUTHORIZATION_ATTR = "remote-authorizations";

    static {
        OIDCAttributeMapperHelper.addIncludeInTokensConfig(configProperties, AttributeOIDCProtocolMapper.class);
        OIDCAttributeMapperHelper.addTokenClaimNameConfig(configProperties);
        configProperties.get(configProperties.size()-1).setDefaultValue("http://www.virtru.com/tdf_claims");

        configProperties.add(new ProviderConfigProperty(REMOTE_URL, "Attribute Provider URL",
                "Full URL of the remote attribute provider service endpoint. Overrides the \"CLAIMS_URL\" environment variable setting",
                ProviderConfigProperty.STRING_TYPE, null));

        configProperties.add(new ProviderConfigProperty(REMOTE_PARAMETERS, "Parameters",
                "List of additional parameters to send separated by '&'. Separate parameter name and value by an equals sign '=', the value can contain equals signs (ex: scope=all&full=true).",
                ProviderConfigProperty.STRING_TYPE, null));

        configProperties.add(new ProviderConfigProperty(REMOTE_PARAMETERS, "Headers",
                "List of headers to send separated by '&'. Separate header name and value by an equals sign '=', the value can contain equals signs (ex: Authorization=az89d).",
                ProviderConfigProperty.STRING_TYPE, null));

        configProperties.add(new ProviderConfigProperty(PUBLIC_KEY_HEADER, "Client Public Key Header Name",
                "Header name containing tdf client public key",
                ProviderConfigProperty.STRING_TYPE, "X-VirtruPubKey"));

    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return configProperties;
    }

    @Override
    public String getDisplayCategory() {
        return TOKEN_MAPPER_CATEGORY;
    }

    @Override
    public String getDisplayType() {
        return "Virtru OIDC to Entity Claim Mapper";
    }

    @Override
    public String getId() {
        return PROVIDER_ID;
    }

    @Override
    public String getHelpText() {
        return "Provides Attribute Custom Claims";
    }


    @Override
    protected void setClaim(IDToken token, ProtocolMapperModel mappingModel, UserSessionModel userSession, KeycloakSession keycloakSession,
                            ClientSessionContext clientSessionCtx) {

        //FIXME We have to override the `sub` property so that it's the user's name/email
        //and not just the Keycloak UID - and the reason we have to do this is because of
        //how legacy code expects `dissems` to work.
        //
        //We will have to fix `dissems` to properly get rid of this hack.
        token.setSubject(userSession.getUser().getId());
        logger.info("Custom claims mapper triggered");
        JsonNode claims = clientSessionCtx.getAttribute(REMOTE_AUTHORIZATION_ATTR, JsonNode.class);
        if (logger.isDebugEnabled()) {
            logger.debug("Fetch remote claims = " + (claims == null));
        }
        // If claims are not cached OR this is a userinfo request (which should always refresh claims from remote)
        // then refresh claims.
        if (claims == null || OIDCAttributeMapperHelper.includeInUserInfo(mappingModel)) {
            logger.debug("Getting remote authorizations");
            claims = getRemoteAuthorizations(mappingModel, userSession, keycloakSession, clientSessionCtx, token);
            clientSessionCtx.setAttribute(REMOTE_AUTHORIZATION_ATTR, claims);
        } else {
            logger.debug("Looks like remote authorizations are already cached, not refreshing...");
            logger.debug("Cached claims are: " + claims);
        }
        OIDCAttributeMapperHelper.mapClaim(token, mappingModel, claims);
    }


    private Map<String, Object> getHeaders(ProtocolMapperModel mappingModel, UserSessionModel userSession) {
        return buildMapFromStringConfig(mappingModel.getConfig().get(REMOTE_HEADERS));
    }

    private Map<String, Object> buildMapFromStringConfig(String config) {
        final Map<String, Object> map = new HashMap<>();

        //FIXME: using MULTIVALUED_STRING_TYPE would be better but it doesn't seem to work
        if (config != null && !"".equals(config.trim())) {
            String[] configList = config.trim().split("&");
            String[] keyValue;
            for (String configEntry : configList) {
                keyValue = configEntry.split("=", 2);
                if (keyValue.length == 2) {
                    map.put(keyValue[0], keyValue[1]);
                }
            }
        }

        return map;
    }

    private Map<String, Object> getRequestParameters(ProtocolMapperModel mappingModel, UserSessionModel userSession, ClientSessionContext clientSessionCtx) throws JsonProcessingException {
        // Get parameters
        final Map<String, Object> formattedParameters = buildMapFromStringConfig(mappingModel.getConfig().get(REMOTE_PARAMETERS));

        //TODO By default, only request absolute minimum claims needed for auth/ID tokens (claims with PoP payload (client public key))
        //String claimReqType = "min_claims";
        //Right now, for back compat, ALWAYS return full claims by default - later, when/if a reduced claimset is needed, we can default to minClaims
        String claimReqType = "full_claims";

        logger.debug("userSession.getNotes CONTENT IS: ");
        for (Map.Entry<String, String> entry : userSession.getNotes().entrySet()) {
            logger.debug("ENTRY IS: " + entry);
        }

        //AZP == clientID (always present)
        //SUB = subject (always present, might be == AZP, might not be )
        // Get client ID (or IDs plural, if this is a token that has been exchanged for the same user from a previous client)
        String clientId = userSession.getAuthenticatedClientSessions().values().stream()
            .map(AuthenticatedClientSessionModel::getClient)
            .map(ClientModel::getId)
            .distinct()
            .collect(Collectors.joining(","));

        logger.debug("Complete list of clients from keycloak is: " + clientId);

        String[] clientIds = clientId.split(",");

        ObjectMapper objectMapper = new ObjectMapper();
        formattedParameters.put("secondary_entity_ids", clientIds);

        // Get username
        // TODO at some point we should probably skip this if it's a service account
        logger.debug("USERNAME value is: " + userSession.getLoginUsername());
        logger.debug("Current User UUID value is: " + userSession.getUser().getId());
        formattedParameters.put("primary_entity_id", userSession.getUser().getId());

        logger.debug("CHECKING USERINFO mapper!");
        // If we are configured to be a protocol mapper for userinfo tokens, then always include full claimset
        if (OIDCAttributeMapperHelper.includeInUserInfo(mappingModel)) {
            logger.debug("USERINFO mapper!");
            claimReqType = "full_claims";
        }

        formattedParameters.put(CLAIM_REQUEST_TYPE, claimReqType);

        return formattedParameters;
    }

    /**
     * Query Attribute-Provider for user's attributes.
     *
     * If no client public key has been provided in the request headers noop occurs.  Otherwise, a request
     * is sent as a simple map json document with keys:
     * - signerPublicKey: the client's public signing key
     * - primary_entity_id: required - identifier for the principal subject claims are being fetched for (PE or NPE)
     * - key/value per parameter configuration.
     * - secondary_entity_ids: required - list of identifiers for any additional secondary subjects claims will be fetched for.
     * @param mappingModel
     * @param userSession
     * @param keycloakSession
     * @return custom claims; null if no client pk present.
     */
    private JsonNode getRemoteAuthorizations(ProtocolMapperModel mappingModel, UserSessionModel userSession,
                                             KeycloakSession keycloakSession, ClientSessionContext clientSessionCtx,
                                             IDToken token) {
        String clientPKHeaderName = mappingModel.getConfig().get(PUBLIC_KEY_HEADER);
        String clientPK = null;
        if (clientPKHeaderName != null) {
            List<String> clientPKList = keycloakSession.getContext().getRequestHeaders().getRequestHeader(clientPKHeaderName);
            clientPK = clientPKList == null || clientPKList.isEmpty() ? null : clientPKList.get(0);
        }
        if (clientPK != null) {
            if (clientPK.startsWith("LS0")) {
                byte[] decodedBytes = Base64.getDecoder().decode(clientPK); 
                clientPK = new String(decodedBytes);
            }
            logger.info("Client Cert: " + clientPK);
        }
        if (clientPK == null) {
            logger.warn("No client cert for: [" + token.getSubject() + "] within [" + token + "]");
            //noop - return
            return null;
        }
        // Call remote service
        ResteasyProviderFactory instance = ResteasyProviderFactory.getInstance();
        RegisterBuiltin.register(instance);
        instance.registerProvider(ResteasyJackson2Provider.class);
        final String url = mappingModel.getConfig().get(REMOTE_URL) == null ? System.getenv("CLAIMS_URL"): mappingModel.getConfig().get(REMOTE_URL);
        logger.info("Request attributes for subject: [" + token.getSubject() + "] within [" + token + "]");
        CloseableHttpResponse response = null;
        try {
            // Get parameters
            Map<String, Object> parameters = getRequestParameters(mappingModel, userSession, clientSessionCtx);
            // Get headers
            Map<String, Object> headers = getHeaders(mappingModel, userSession);
            headers.put("Content-Type", "application/json");

            if(url == null){
                throw new Exception(REMOTE_URL + " property is not set via an env variable or configuration value");
            }

            HttpPost httpReq = new HttpPost(url);
            URIBuilder uriBuilder = new URIBuilder(httpReq.getURI());
            httpReq.setURI(uriBuilder.build());
            Map<String, Object> requestEntity = new HashMap<>();
            requestEntity.put("algorithm", "ec:secp256r1");
            requestEntity.put("signerPublicKey", clientPK);
            logger.info("Request: " + requestEntity);

            // Build parameters
            for (Map.Entry<String, Object> param : parameters.entrySet()) {
                requestEntity.put(param.getKey(), param.getValue());
            }
            // Build headers
            for (Map.Entry<String, Object> header : headers.entrySet()) {
                httpReq.setHeader(header.getKey(), header.getValue().toString());
            }
            ObjectMapper objectMapper = new ObjectMapper();
            httpReq.setEntity(new StringEntity(objectMapper.writeValueAsString(requestEntity)));

            response = client.execute(httpReq);
            String bodyAsString = EntityUtils.toString(response.getEntity());
            if (response.getStatusLine().getStatusCode() != 200) {
                logger.warn(response.getStatusLine() + "" + bodyAsString);
                throw new Exception("Wrong status received for remote claim - Expected: 200, Received: " + response.getStatusLine().getStatusCode() + ":" + url);
            }
            logger.debug(bodyAsString);
            return objectMapper.readValue(bodyAsString, JsonNode.class);
        } catch (Exception e) {
            logger.error("Error", e);
            // exceptions are thrown to prevent token from being delivered without all information
            throw new JsonRemoteClaimException("Error when accessing remote claim", url, e);
        } finally {
            try {
                if (response != null) {
                    response.close();
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        }
    }

}
