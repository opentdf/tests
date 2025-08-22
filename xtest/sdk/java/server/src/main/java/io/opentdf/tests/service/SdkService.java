package io.opentdf.tests.service;

import io.opentdf.platform.sdk.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
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
            
            // Use SDKBuilder to create SDK instance
            SDKBuilder builder = SDKBuilder.newBuilder();
            
            // Configure the SDK based on the endpoint protocol
            if (platformEndpoint.startsWith("http://")) {
                // Extract host:port from URL
                String hostPort = platformEndpoint.replace("http://", "");
                sdkClient = builder
                    .platformEndpoint(hostPort)
                    .clientSecret(clientId, clientSecret)
                    .useInsecurePlaintextConnection(true)
                    .build();
            } else {
                // HTTPS endpoint
                String hostPort = platformEndpoint.replace("https://", "");
                sdkClient = builder
                    .platformEndpoint(hostPort)
                    .clientSecret(clientId, clientSecret)
                    .build();
            }
            
            logger.info("Java SDK client initialized successfully");
        } catch (Exception e) {
            logger.error("Failed to initialize SDK client", e);
            throw new RuntimeException("Failed to initialize SDK client", e);
        }
    }
    
    public byte[] encrypt(byte[] data, List<String> attributes, String format) throws Exception {
        logger.info("Encrypting data with format: {} and attributes: {}", format, attributes);
        
        // Create KAS configuration
        var kasInfo = new Config.KASInfo();
        kasInfo.URL = kasEndpoint;
        
        // Create TDF configuration with attributes
        Config.TDFConfig tdfConfig;
        if (attributes != null && !attributes.isEmpty()) {
            tdfConfig = Config.newTDFConfig(
                Config.withKasInformation(kasInfo),
                Config.withDataAttributes(attributes.toArray(new String[0]))
            );
        } else {
            tdfConfig = Config.newTDFConfig(
                Config.withKasInformation(kasInfo)
            );
        }
        
        // Create input stream from data
        ByteArrayInputStream inputStream = new ByteArrayInputStream(data);
        
        // Create output stream for encrypted data
        ByteArrayOutputStream outputStream = new ByteArrayOutputStream();
        
        // Create TDF
        Manifest manifest = sdkClient.createTDF(inputStream, outputStream, tdfConfig);
        
        logger.info("Successfully encrypted data, manifest: {}", manifest);
        
        return outputStream.toByteArray();
    }
    
    public byte[] decrypt(byte[] tdfData) throws Exception {
        logger.info("Decrypting TDF data of size: {}", tdfData.length);
        
        // Create a SeekableByteChannel from the byte array
        java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(tdfData);
        java.nio.channels.SeekableByteChannel channel = new java.nio.channels.SeekableByteChannel() {
            private int position = 0;
            
            @Override
            public int read(java.nio.ByteBuffer dst) {
                if (position >= buffer.limit()) {
                    return -1;
                }
                int remaining = Math.min(dst.remaining(), buffer.limit() - position);
                for (int i = 0; i < remaining; i++) {
                    dst.put(buffer.get(position++));
                }
                return remaining;
            }
            
            @Override
            public int write(java.nio.ByteBuffer src) {
                throw new UnsupportedOperationException("Write not supported");
            }
            
            @Override
            public long position() {
                return position;
            }
            
            @Override
            public java.nio.channels.SeekableByteChannel position(long newPosition) {
                position = (int) newPosition;
                return this;
            }
            
            @Override
            public long size() {
                return buffer.limit();
            }
            
            @Override
            public java.nio.channels.SeekableByteChannel truncate(long size) {
                throw new UnsupportedOperationException("Truncate not supported");
            }
            
            @Override
            public boolean isOpen() {
                return true;
            }
            
            @Override
            public void close() {
                // No-op
            }
        };
        
        // Read TDF and get reader
        var reader = sdkClient.loadTDF(channel, Config.newTDFReaderConfig());
        
        // Read the decrypted payload
        ByteArrayOutputStream decryptedOutput = new ByteArrayOutputStream();
        reader.readPayload(decryptedOutput);
        
        byte[] decryptedData = decryptedOutput.toByteArray();
        logger.info("Successfully decrypted data, size: {}", decryptedData.length);
        
        return decryptedData;
    }
    
    public SDK getSdkClient() {
        return sdkClient;
    }
}