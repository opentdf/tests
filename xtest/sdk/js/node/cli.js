/**
 * Simple command-line interface for the TDF3 javascript SDK.
 *
 * Usage:
 *  `node cli.js <encrypt | decrypt> -i <src-file> -o <dst-file>`
 *
 * Plaintext is written as UTF8, ciphertext is written as binary.
 */
const { Command } = require("commander");
const { Readable } = require("stream");
const { FileClient } = require("@opentdf/client");
const fs = require("fs");

const program = new Command();

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

const createClient = () =>
  new Client.Client({
    clientId: "tdf-client",
    clientSecret: "123-456",
    oidcOrigin: "http://localhost:8080/auth/realms/tdf",
    kasEndpoint: "http://localhost:65432/api/kas",
  });

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

const encrypt = () => {
  const { srcFile, dstFile } = program.opts();
  const client = createClient();

  client.encrypt(srcFile).then(ct => ct.toFile(dstFile)).then(done);
};

const decrypt = () => {
  const { srcFile, dstFile } = program.opts();
  const client = createClient();

  client.decrypt(srcFile).then(ct => ct.toFile(dstFile)).then(done);
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
  createClient()
    .decrypt(decryptParams)
    .then((pt) => {
      let rewrapped = false;
      pt.on("rewrap", (metadata) => {
        rewrapped = true;
        jsonToDst(metadata, program.dstFile);
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
  createClient()
    .decrypt(decryptParams)
    .then((pt) => {
      let rewrapped = false;
      pt.on("manifest", (manifest) => {
        rewrapped = true;
        jsonToDst(manifest, program.dstFile);
        done();
        if (process) {
          process.exit();
        }
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

program
  .option("-i, --srcFile <path>", "input file")
  .option("-o, --dstFile <path>", "output file");

program
  .command("encrypt")
  .option(`-m, --mimeType <mimeType>`, "Content Type to apply to the file")
  .action(encrypt);

program.command("decrypt").action(decrypt);

program.command("metadata").action(metadata);

program.command("manifest").action(manifest);

program.parse(process.argv);
