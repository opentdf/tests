/**
 * Simple command-line interface for the TDF3 javascript SDK.
 *
 * Usage:
 *  `node cli.js -s <stage> <encrypt | decrypt> -i <src-file> -o <dst-file>`
 *
 * Plaintext is written as UTF8, ciphertext is written as binary.
 */
const { Command } = require("commander");
const { Readable } = require("stream");
const { Client } = require("tdf3-js");
const fs = require("fs");

const program = new Command();

const config = JSON.parse(
  fs.readFileSync("config-oss.json", { encoding: "utf-8" })
);

const done = () => process.stderr.write("completed cli.js \n");

const setSourceFor = (builder, source) => {
  if (source instanceof Readable) {
    builder.setStreamSource(source);
  } else if (source) {
    builder.setFileSource(source);
  } else {
    builder.setStreamSource(process.stdin);
  }
  return builder;
};

const clientFor = program => {
  // const stageName = program.clientOptions;
  // if (!stageName || !config[stageName]) {
  //   console.error(
  //     `Invalid stage [${stageName}]; must be one of ${Object.keys(config)}`
  //   );
  //   return {};
  // }
  // const clientOptions = {
  //   ...config[stageName],
  //   email: process.env.VIRTRU_SDK_EMAIL,
  //   appId: process.env.VIRTRU_SDK_APP_ID || ""
  //   // TODO: Set up local eas client for inbox testing.
  // };
  // if (program.userId) {
  //   clientOptions.userId = program.userId;
  //   clientOptions.email = program.userId;
  // }
  // const safeConfig = {
  //   ...clientOptions,
  //   appId: "*".repeat(clientOptions.appId.length)
  // };

  const safeConfig = {
    clientId: "tdf-client",
    organizationName: 'tdf',
    kasEndpoint: 'http://localhost:8000',
    clientSecret: '123-456',
    virtruOIDCEndpoint: 'http://localhost:65432/keycloak/',
  };

  return new Client.Client(safeConfig);
};

 const dstAsStream = (dstFile, encoding) => {
   if (dstFile) {
     let opts = { flag: "w" };
     if (encoding) {
       opts.encoding = encoding;
     }
     return fs.createWriteStream(dstFile, opts);
   }
   return process.stdout;
 };

const encrypt = ({ mimeType }) => {
  const { srcFile, dstFile } = program.opts();

  const encryptParamsBuilder = setSourceFor(
    new Client.EncryptParamsBuilder(),
    srcFile
  );

  if (mimeType) {
    encryptParamsBuilder.setMimeType(mimeType);
  }

  encryptParamsBuilder.withOffline();
  const client = clientFor(program);

  const encryptParams = encryptParamsBuilder.build();

  client.encrypt(encryptParams).then(ct => {
    ct.pipe(dstAsStream(dstFile, "binary"));
    ct.on("end", done);
  });
};

const decrypt = () => {
  const { srcFile, dstFile } = program.opts();

  const decryptParams = setSourceFor(
      new Client.DecryptParamsBuilder(),
      srcFile
  ).build();

  const client = clientFor(program);

  client.decrypt(decryptParams).then(pt => {
    pt.pipe(dstAsStream(dstFile, "utf8"));
    pt.on("end", done);
  });
};

const jsonToDst = (value, dstFile) => {
  let json;
  try {
    json = JSON.stringify(value, null, 2);
  } catch (e) {
    console.warn(`Error while serializing value: ${e};\n\tretrying...`);
    json = require("util").inspect(value);
  }
  if (dstFile) {
    fs.writeFileSync(dstFile, json);
  } else {
    process.stdout.write(json);
  }
};

const metadata = () => {
  const decryptParams = setSourceFor(
    new Client.DecryptParamsBuilder(),
    program.srcFile
  ).build();
  clientFor(program)
    .decrypt(decryptParams)
    .then(pt => {
      let rewrapped = false;
      pt.on("rewrap", metadata => {
        rewrapped = true;
        jsonToDst(metadata, program.dstFile);
      });
      pt.on("data", chunk => {
        /* ignored */
      });
      pt.on("end", () => {
        if (!rewrapped && !pt.metadata) {
          process.stderr.write(`No metadata found\n`);
          process.exit(2);
        } else if (pt.metadata) {
          jsonToDst(pt.metadata, program.dstFile);
        }
        done();
      });
    });
};

const manifest = () => {
  const decryptParams = setSourceFor(
    new Client.DecryptParamsBuilder(),
    program.srcFile
  ).build();
  clientFor(program)
    .decrypt(decryptParams)
    .then(pt => {
      let rewrapped = false;
      pt.on("manifest", manifest => {
        rewrapped = true;
        jsonToDst(manifest, program.dstFile);
        done();
        if (process) {
          process.exit();
        }
      });
      pt.on("data", () => {
        /* ignored */
      });
      pt.on("end", () => {
        if (!rewrapped && !pt.manifest) {
          process.stderr.write(`No manifest found\n`);
          process.exit(2);
        } else if (pt.manifest) {
          jsonToDst(pt.manifest, program.dstFile);
        }
        done();
      });
    });
};

const pretty_keys = o => `${Object.keys(o).join(" | ")}`;

program
  .option("-i, --srcFile <path>", "input file")
  .option("-o, --dstFile <path>", "output file")
  .requiredOption(`-s, --clientOptions <stage name>`, pretty_keys(config));

program
  .command("encrypt")
  .option(`-m, --mimeType <mimeType>`, "Content Type to apply to the file")
  .option("-a, --attrs <attributeType>", "the type of attributes to be used")
  .action(encrypt);

program.command("decrypt").action(decrypt);

program.command("metadata").action(metadata);

program.command("manifest").action(manifest);

program.parse(process.argv);