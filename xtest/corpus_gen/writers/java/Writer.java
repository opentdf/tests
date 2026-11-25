// Corpus writer for the Java SDK. Reads a JSON array of WriteJobs and writes one
// TDF per job. See corpus_gen/selfcheck.py for the job shape.
//
//   java -cp sdk/java/dist/main/cmdline.jar Writer.java <jobs.json>
//
// Needs PLATFORMURL, CLIENTID and CLIENTSECRET.

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.nimbusds.jose.util.Base64;
import io.opentdf.platform.sdk.AssertionConfig;
import io.opentdf.platform.sdk.Config;
import io.opentdf.platform.sdk.KeyType;
import io.opentdf.platform.sdk.SDK;
import io.opentdf.platform.sdk.SDKBuilder;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

public class Writer {
    static final int MIN_SEGMENT_SIZE = 16 * 1024;
    static final int MAX_SEGMENT_SIZE = 4 * 1024 * 1024;

    static final Set<String> JOB_FIELDS = Set.of("out", "plaintext", "kas", "split", "attributes",
            "segment_size", "mime_type", "encrypted_metadata", "assertions", "target_mode");
    static final Set<String> KAS_FIELDS = Set.of("url", "kid", "alg");
    static final Set<String> SPLIT_FIELDS = Set.of("kas", "sid");
    static final Set<String> ASSERTION_FIELDS = Set.of("kind", "alg", "key_pem", "x5c", "id", "scope",
            "applies_to_state", "statement");
    static final Set<String> SHAPE_FIELDS = Set.of("id", "scope", "applies_to_state", "statement");
    static final Set<String> STATEMENT_FIELDS = Set.of("format", "schema", "value");

    static JsonObject object(JsonElement e, String what, Set<String> allowed) {
        if (!e.isJsonObject()) {
            throw new IllegalArgumentException(what + " must be an object");
        }
        for (String k : e.getAsJsonObject().keySet()) {
            if (!allowed.contains(k)) {
                throw new IllegalArgumentException("unknown field \"" + k + "\" in " + what);
            }
        }
        return e.getAsJsonObject();
    }

    static String str(JsonObject o, String key) {
        JsonElement e = o.get(key);
        if (e == null || e.isJsonNull()) {
            return null;
        }
        if (!e.isJsonPrimitive() || !e.getAsJsonPrimitive().isString()) {
            throw new IllegalArgumentException(key + " must be a string");
        }
        return e.getAsString();
    }

    static String requireStr(JsonObject o, String key) {
        String s = str(o, key);
        if (s == null) {
            throw new IllegalArgumentException("missing " + key);
        }
        return s;
    }

    static long integer(JsonElement e, String key) {
        if (!e.isJsonPrimitive() || !e.getAsJsonPrimitive().isNumber()) {
            throw new IllegalArgumentException(key + " must be an integer");
        }
        try {
            return new java.math.BigDecimal(e.getAsString()).longValueExact();
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(key + " must be an integer");
        }
    }

    static JsonArray array(JsonObject o, String key) {
        JsonElement e = o.get(key);
        if (e == null || e.isJsonNull()) {
            return new JsonArray();
        }
        if (!e.isJsonArray()) {
            throw new IllegalArgumentException(key + " must be an array");
        }
        return e.getAsJsonArray();
    }

    static byte[] pemBody(String pem, String type) {
        String begin = "-----BEGIN " + type + "-----";
        String end = "-----END " + type + "-----";
        int b = pem.indexOf(begin);
        int e = pem.indexOf(end);
        if (b < 0 || e < b) {
            throw new IllegalArgumentException("not a PEM " + type);
        }
        String body = pem.substring(b + begin.length(), e).replaceAll("\\s", "");
        return java.util.Base64.getDecoder().decode(body);
    }

    static PrivateKey rsaKey(String pem) throws Exception {
        if (pem.contains("BEGIN RSA PRIVATE KEY")) {
            throw new IllegalArgumentException("key_pem must be PKCS#8 (BEGIN PRIVATE KEY)");
        }
        return KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(pemBody(pem, "PRIVATE KEY")));
    }

    static String nonEmpty(JsonObject o, String key, String what) {
        String s = requireStr(o, key);
        if (s.isEmpty()) {
            throw new IllegalArgumentException(what + " " + key + " must not be empty");
        }
        return s;
    }

    /** Applies the optional id, scope, applies_to_state and statement. */
    static void handlingShape(JsonObject a, AssertionConfig cfg) {
        if (str(a, "id") != null) {
            cfg.id = nonEmpty(a, "id", "assertion");
        }
        String scope = str(a, "scope");
        if (scope != null) {
            cfg.scope = switch (scope) {
                case "tdo" -> AssertionConfig.Scope.TrustedDataObj;
                case "payload" -> AssertionConfig.Scope.Payload;
                default -> throw new IllegalArgumentException("scope \"" + scope + "\" not one of tdo, payload");
            };
        }
        String state = str(a, "applies_to_state");
        if (state != null) {
            cfg.appliesToState = switch (state) {
                case "encrypted" -> AssertionConfig.AppliesToState.Encrypted;
                case "unencrypted" -> AssertionConfig.AppliesToState.Unencrypted;
                default -> throw new IllegalArgumentException(
                        "applies_to_state \"" + state + "\" not one of encrypted, unencrypted");
            };
        }
        JsonElement st = a.get("statement");
        if (st != null && !st.isJsonNull()) {
            JsonObject s = object(st, "statement", STATEMENT_FIELDS);
            cfg.statement = new AssertionConfig.Statement();
            cfg.statement.format = nonEmpty(s, "format", "statement");
            cfg.statement.schema = nonEmpty(s, "schema", "statement");
            cfg.statement.value = nonEmpty(s, "value", "statement");
        }
    }

    /** Returns null for system-metadata, which has its own option. */
    static AssertionConfig assertion(JsonObject a) throws Exception {
        String kind = requireStr(a, "kind");
        if (kind.equals("system-metadata")) {
            for (String k : SHAPE_FIELDS) {
                if (a.has(k) && !a.get(k).isJsonNull()) {
                    throw new IllegalArgumentException("system-metadata takes no " + k + "; the SDK builds it");
                }
            }
            return null;
        }
        if (!kind.equals("handling")) {
            throw new IllegalArgumentException("unknown assertion kind \"" + kind + "\"");
        }
        String alg = requireStr(a, "alg");
        String keyPem = requireStr(a, "key_pem");
        JsonArray x5c = array(a, "x5c");

        var cfg = new AssertionConfig();
        cfg.id = "handling-" + alg.toLowerCase();
        cfg.type = AssertionConfig.Type.HandlingAssertion;
        cfg.scope = AssertionConfig.Scope.TrustedDataObj;
        cfg.appliesToState = AssertionConfig.AppliesToState.Encrypted;
        cfg.statement = new AssertionConfig.Statement();
        cfg.statement.format = "json";
        cfg.statement.schema = "urn:corpus:handling";
        cfg.statement.value = "{\"handling\":\"corpus\"}";
        handlingShape(a, cfg);
        switch (alg) {
            case "HS256" -> {
                if (x5c.size() > 0) {
                    throw new IllegalArgumentException("x5c requires an RS256 handling assertion");
                }
                cfg.signingKey = new AssertionConfig.AssertionKey(AssertionConfig.AssertionKeyAlg.HS256,
                        keyPem.getBytes(StandardCharsets.UTF_8));
            }
            case "RS256" -> {
                cfg.signingKey = new AssertionConfig.AssertionKey(AssertionConfig.AssertionKeyAlg.RS256, rsaKey(keyPem));
                if (x5c.size() > 0) {
                    List<Base64> chain = new ArrayList<>();
                    for (JsonElement c : x5c) {
                        if (!c.isJsonPrimitive() || !c.getAsJsonPrimitive().isString()) {
                            throw new IllegalArgumentException("x5c entries must be PEM strings");
                        }
                        chain.add(Base64.encode(pemBody(c.getAsString(), "CERTIFICATE")));
                    }
                    cfg.signingKey.withX5c(chain);
                }
            }
            default -> throw new IllegalArgumentException("unsupported handling alg \"" + alg + "\"");
        }
        return cfg;
    }

    /**
     * Maps kas/split onto withKasInformation. The SDK names splits itself (random UUIDs
     * for several KAS, none for one) and KeySplitStep is not constructible outside the
     * SDK, so explicit sids cannot be written; split may only order the KAS list.
     */
    static List<Consumer<Config.TDFConfig>> kasOptions(JsonObject job) {
        JsonArray kas = array(job, "kas");
        if (kas.size() == 0) {
            throw new IllegalArgumentException("need kas or attributes");
        }
        List<Config.KASInfo> infos = new ArrayList<>();
        for (JsonElement e : kas) {
            JsonObject k = object(e, "kas entry", KAS_FIELDS);
            var info = new Config.KASInfo();
            info.URL = requireStr(k, "url");
            info.KID = str(k, "kid");
            info.Algorithm = str(k, "alg");
            infos.add(info);
        }
        JsonArray split = array(job, "split");
        if (split.size() > 0) {
            if (split.size() != infos.size()) {
                throw new IllegalArgumentException("split must name every kas exactly once");
            }
            List<Config.KASInfo> ordered = new ArrayList<>();
            Set<Integer> seen = new HashSet<>();
            for (JsonElement e : split) {
                JsonObject s = object(e, "split entry", SPLIT_FIELDS);
                String sid = str(s, "sid");
                if (sid != null && !sid.isEmpty()) {
                    throw new IllegalArgumentException("Java SDK " + version()
                            + " assigns split ids itself; cannot write sid \"" + sid + "\"");
                }
                if (!s.has("kas") || s.get("kas").isJsonNull()) {
                    throw new IllegalArgumentException("split entry missing kas");
                }
                long idx = integer(s.get("kas"), "split kas");
                if (idx < 0 || idx >= infos.size() || !seen.add((int) idx)) {
                    throw new IllegalArgumentException("split must name every kas exactly once");
                }
                ordered.add(infos.get((int) idx));
            }
            infos = ordered;
        }
        List<Consumer<Config.TDFConfig>> opts = new ArrayList<>();
        opts.add(Config.withAutoconfigure(false));
        opts.add(Config.withKasInformation(infos.toArray(new Config.KASInfo[0])));
        // A single KAS takes its key algorithm from the wrapping key type.
        String alg = infos.get(0).Algorithm;
        if (infos.size() == 1 && alg != null) {
            opts.add(Config.WithWrappingKeyAlg(KeyType.fromString(alg)));
        }
        return opts;
    }

    static List<Consumer<Config.TDFConfig>> options(JsonObject job) throws Exception {
        List<Consumer<Config.TDFConfig>> opts = new ArrayList<>();
        JsonArray attrs = array(job, "attributes");
        if (attrs.size() > 0) {
            String[] fqns = new String[attrs.size()];
            for (int i = 0; i < fqns.length; i++) {
                if (!attrs.get(i).isJsonPrimitive() || !attrs.get(i).getAsJsonPrimitive().isString()) {
                    throw new IllegalArgumentException("attributes must be strings");
                }
                fqns[i] = attrs.get(i).getAsString();
            }
            opts.add(Config.withDataAttributes(fqns));
            opts.add(Config.withAutoconfigure(true));
        } else {
            opts.addAll(kasOptions(job));
        }
        JsonElement seg = job.get("segment_size");
        if (seg != null && !seg.isJsonNull()) {
            long size = integer(seg, "segment_size");
            if (size < MIN_SEGMENT_SIZE || size > MAX_SEGMENT_SIZE) {
                throw new IllegalArgumentException("segment_size " + size + " outside [" + MIN_SEGMENT_SIZE + ", "
                        + MAX_SEGMENT_SIZE + "]");
            }
            opts.add(Config.withSegmentSize((int) size));
        }
        String mime = str(job, "mime_type");
        if (mime != null) {
            opts.add(Config.withMimeType(mime));
        }
        String meta = str(job, "encrypted_metadata");
        if (meta != null) {
            // The SDK drops blank metadata without a word.
            if (meta.isBlank()) {
                throw new IllegalArgumentException("encrypted_metadata must not be blank");
            }
            opts.add(Config.withMetaData(meta));
        }
        String mode = str(job, "target_mode");
        if (mode != null) {
            opts.add(Config.withTargetMode(mode));
        }
        List<AssertionConfig> cfgs = new ArrayList<>();
        Set<String> ids = new HashSet<>();
        for (JsonElement e : array(job, "assertions")) {
            AssertionConfig cfg = assertion(object(e, "assertion", ASSERTION_FIELDS));
            String id = cfg == null ? "system-metadata" : cfg.id;
            if (!ids.add(id)) {
                throw new IllegalArgumentException("duplicate assertion id \"" + id + "\"");
            }
            if (cfg == null) {
                opts.add(Config.withSystemMetadataAssertion());
            } else {
                cfgs.add(cfg);
            }
        }
        if (!cfgs.isEmpty()) {
            opts.add(Config.withAssertionConfig(cfgs.toArray(new AssertionConfig[0])));
        }
        return opts;
    }

    static String version() {
        String v = SDK.class.getPackage().getImplementationVersion();
        return v == null ? "unknown" : v;
    }

    static void write(SDK sdk, JsonObject job) throws Exception {
        List<Consumer<Config.TDFConfig>> opts = options(job);
        byte[] plain = Files.readAllBytes(Path.of(requireStr(job, "plaintext")));
        var out = new ByteArrayOutputStream();
        @SuppressWarnings("unchecked")
        Consumer<Config.TDFConfig>[] arr = opts.toArray(new Consumer[0]);
        sdk.createTDF(new ByteArrayInputStream(plain), out, Config.newTDFConfig(arr));
        Path dest = Path.of(requireStr(job, "out"));
        if (dest.getParent() != null) {
            Files.createDirectories(dest.getParent());
        }
        Files.write(dest, out.toByteArray());
    }

    static int run(String path) throws Exception {
        JsonElement root = JsonParser.parseString(Files.readString(Path.of(path)));
        if (!root.isJsonArray()) {
            throw new IllegalArgumentException("parse " + path + ": expected a JSON array");
        }
        // Strict decode of every job up front, as the Go writer does.
        List<JsonObject> jobs = new ArrayList<>();
        for (JsonElement e : root.getAsJsonArray()) {
            jobs.add(object(e, "job", JOB_FIELDS));
        }

        String platform = System.getenv("PLATFORMURL");
        String id = System.getenv("CLIENTID");
        String secret = System.getenv("CLIENTSECRET");
        if (platform == null || platform.isEmpty() || id == null || id.isEmpty() || secret == null
                || secret.isEmpty()) {
            throw new IllegalArgumentException("PLATFORMURL, CLIENTID and CLIENTSECRET must be set");
        }
        SDK sdk = new SDKBuilder().platformEndpoint(platform).clientSecret(id, secret)
                .useInsecurePlaintextConnection(platform.startsWith("http://")).build();

        boolean failed = false;
        for (JsonObject job : jobs) {
            String out = job.has("out") && job.get("out").isJsonPrimitive() ? job.get("out").getAsString() : "";
            try {
                write(sdk, job);
            } catch (Exception | LinkageError e) {
                System.err.println("job " + out + ": " + e);
                failed = true;
                continue;
            }
            JsonObject line = new JsonObject();
            line.addProperty("out", out);
            line.addProperty("sdk", "java");
            line.addProperty("version", version());
            System.out.println(line);
        }
        return failed ? 1 : 0;
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("usage: Writer.java <jobs.json>");
            System.exit(2);
        }
        int code;
        try {
            code = run(args[0]);
        } catch (Exception e) {
            System.err.println(e);
            code = 1;
        }
        // The SDK's channels keep non-daemon threads alive.
        System.exit(code);
    }
}
