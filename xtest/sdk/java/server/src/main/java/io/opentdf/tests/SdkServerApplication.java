package io.opentdf.tests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestTemplate;

@SpringBootApplication
public class SdkServerApplication {

    public static void main(String[] args) {
        // Check for daemon mode
        boolean daemonize = false;
        for (String arg : args) {
            if ("--daemonize".equals(arg) || "-d".equals(arg)) {
                daemonize = true;
                break;
            }
        }

        // Start the application
        SpringApplication app = new SpringApplication(SdkServerApplication.class);
        
        // Set port from environment or default
        String port = System.getenv("JAVA_SDK_PORT");
        if (port == null) {
            port = "8092";
        }
        System.setProperty("server.port", port);
        
        // Run the application
        app.run(args);
        
        System.out.println("Java SDK server started on port " + port);
    }

    @Bean
    public RestTemplate restTemplate() {
        return new RestTemplate();
    }
}