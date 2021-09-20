import java.io.File;
import java.io.FileReader;
import java.util.Map;
import java.util.Arrays;
import java.util.Vector;

import org.json.simple.JSONArray;
import org.json.simple.JSONObject;
import org.json.simple.parser.*;

import org.scijava.nativelib.NativeLoader;

import com.virtru.*;

public class osstdf3 {
   public static void main(String argv[]) throws Exception {

       NativeLoader.loadLibrary("tdf3-java");

       String stage = argv[0];
       String source = argv[1];
       String target = argv[2];
       String owner = argv[3];
       String action = argv[4];

       Object obj = new JSONParser().parse(new FileReader("config-oss.json"));
       JSONObject jo = (JSONObject) obj;

       Map config = ((Map)jo.get(stage));
       
       String eas = (String)config.get("entityObjectEndpoint");
       String ending = "/v1/entity_object";
       if(eas.endsWith(ending)){
           eas = eas.substring(0, eas.length() - ending.length());
       }
       
       String ca = System.getenv("TDF3_CERT_AUTHORITY");
       TDF3Client client;
       if(ca!=null){
           String client_path = System.getenv("CERT_CLIENT_BASE");
           if(client_path==null){client_path = "/xtest/client";}

           client = new TDF3Client(eas,owner, client_path + ".key", client_path + ".crt", ca, false);
       }
       else{
           client = new TDF3Client(eas, owner);
       }
       client.enableConsoleLogging(virtru.LogLevel_Info);


       if(action.equals("decrypt")){
           decrypt(source, target, client);
       }
       else{
           String attributes = "";
           if(argv.length>=8 && argv[7]=="--attrs"){
                attributes = argv[8];
                String[] encryptAttrs = new String [0];
                if(attributes=="Success Attributes"){
                    encryptAttrs= new String[]{"http://example.com/attr/language/value/urduTest","http://example.com/attr/language/value/frenchTest"};

                }
                else if(attributes=="Failing Attributes"){
                    encryptAttrs= new String[]{"http://example.com/attr/language/value/urduTest","http://example.com/attr/language/value/germanTest"};
                }
                encrypt(source, target, client, encryptAttrs);
           }
           else{
               encrypt(source, target, client, new String[0]);
           }
           
       }
              
       File index = new File("./tmplib");
       index.deleteOnExit();

   }

   public static void encrypt(String source, String target, TDF3Client client, String[] attrs) throws Exception {
       StringVector v = new StringVector(attrs);
       client.withDataAttributes(v);
       client.encryptFile(source, target);
   }

   public static void decrypt(String source, String target, TDF3Client client) throws Exception {
       client.decryptFile(source, target);

   }
}

