package io.opentdf.tests.service;

import io.opentdf.platform.sdk.Config;
import io.opentdf.platform.sdk.NanoTDF;
import io.opentdf.platform.sdk.SDK;
import io.opentdf.platform.sdk.TDF;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.nio.ByteBuffer;
import java.util.Base64;
import java.util.List;

@Service
public class SdkService {
    
    private static final Logger logger = LoggerFactory.getLogger(SdkService.class);
    
    @Value("${platform.endpoint:http://localhost:8080}")
    private String platformEndpoint;
    
    @Value("${kas.endpoint:http://localhost:8080/kas}")
    private String kasEndpoint;
    
    @Value("${oidc.endpoint:http://localhost:8888/auth}")
    private String oidcEndpoint;
    
    @Value("${client.id:opentdf}")
    private String clientId;
    
    @Value("${client.secret:secret}")
    private String clientSecret;
    
    private SDK sdkClient;
    
    @PostConstruct
    public void initialize() {
        try {
            logger.info("Initializing Java SDK client");
            logger.info("Platform endpoint: {}", platformEndpoint);
            logger.info("KAS endpoint: {}", kasEndpoint);
            logger.info("OIDC endpoint: {}", oidcEndpoint);
            
            Config config = Config.builder()
                .kasEndpoint(kasEndpoint)
                .platformEndpoint(platformEndpoint)
                .oidcEndpoint(oidcEndpoint)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();
            
            sdkClient = new SDK(config);
            logger.info("Java SDK client initialized successfully");
        } catch (Exception e) {
            logger.error("Failed to initialize SDK client", e);
            throw new RuntimeException("Failed to initialize SDK client", e);
        }
    }
    
    public byte[] encrypt(byte[] data, List<String> attributes, String format) throws Exception {
        logger.info("Encrypting data with format: {}", format);
        
        if ("nano".equalsIgnoreCase(format)) {
            NanoTDF nanoTDF = new NanoTDF();
            nanoTDF.createNanoTDF(
                ByteBuffer.wrap(data),
                kasEndpoint,
                attributes.toArray(new String[0])
            );
            return nanoTDF.getSerializedNanoTDF();
        } else {
            // Default to standard TDF
            TDF tdf = new TDF();
            tdf.createTDF(
                data,
                kasEndpoint,
                attributes.toArray(new String[0])
            );
            return tdf.getSerializedTDF();
        }
    }
    
    public byte[] decrypt(byte[] tdfData) throws Exception {
        logger.info("Decrypting TDF data");
        
        // Try to detect format (simplified - real implementation would check magic bytes)
        if (isNanoTDF(tdfData)) {
            NanoTDF nanoTDF = new NanoTDF();
            nanoTDF.loadNanoTDF(ByteBuffer.wrap(tdfData));
            ByteBuffer decrypted = nanoTDF.getPayload();
            byte[] result = new byte[decrypted.remaining()];
            decrypted.get(result);
            return result;
        } else {
            TDF tdf = new TDF();
            tdf.loadTDF(tdfData);
            return tdf.getPayload();
        }
    }
    
    private boolean isNanoTDF(byte[] data) {
        // Simple heuristic - NanoTDF is typically smaller and has different structure
        // Real implementation would check magic bytes/headers
        return data.length < 1024 && data[0] == 0x4C; // 'L' for L1
    }
    
    public SDK getSdkClient() {
        return sdkClient;
    }
}