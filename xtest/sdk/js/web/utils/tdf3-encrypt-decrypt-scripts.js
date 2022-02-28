const virtru = require("tdf3-js");

async function encrypt(file) {
  const client = new virtru.Client.Client(window.creds);
  const encryptParams = new virtru.Client.EncryptParamsBuilder()
    .withArrayBufferSource(await file.arrayBuffer())
    .withOffline()
    .build();
  const ct = await client.encrypt(encryptParams);
  const ciphertext = await ct.toString();
  const a = document.getElementById("download_link_encrypted");

  a.href = `data:application/octet-stream;charset=utf-8;base64,${btoa(
    ciphertext
  )}`;
  a.download = window.creds.dstFile.split("/").pop();
  a.click();
}

async function decrypt(file) {
  const client = new virtru.Client.Client(window.creds);
  const decryptParams = new virtru.Client.DecryptParamsBuilder()
    .withArrayBufferSource(await file.arrayBuffer())
    .build();
  const dt = await client.decrypt(decryptParams);

  const b64dt = await dt.toString("base64");
  const a = document.getElementById("download_link_decrypted");

  a.href = `data:application/octet-stream;charset=utf-8;base64,${b64dt}`;
  a.download = window.creds.dstFile.split("/").pop();
  a.click();
}

async function metadata(file) {
  const client = new virtru.Client.Client(window.creds);
  const decryptParams = new virtru.Client.DecryptParamsBuilder()
    .withArrayBufferSource(await file.arrayBuffer())
    .build();
  const dt = await client.decrypt(decryptParams);

  const metadata = JSON.stringify(await dt.getMetadata());
  const a = document.getElementById("download_link_metadata");

  a.href = `data:application/octet-stream;charset=utf-8;base64,${btoa(
    metadata
  )}`;
  a.download = window.creds.dstFile.split("/").pop();
  a.click();
}

async function manifest(file) {
  const tdf = new virtru.TDF();
  await tdf.loadTDFStream({ location: file, type: "file-browser" });
  const a = document.getElementById("download_link_manifest");

  a.href = `data:application/octet-stream;charset=utf-8;base64,${btoa(
    JSON.stringify(tdf.manifest)
  )}`;
  a.download = window.creds.dstFile.split("/").pop();
  a.click();
}

const encryptInput = document.getElementById("encrypt");
encryptInput.addEventListener(
  "change",
  function(e) {
    e.preventDefault();
    encrypt(this.files[0]);
  },
  false
);

const decryptInput = document.getElementById("decrypt");
decryptInput.addEventListener(
  "change",
  function(e) {
    e.preventDefault();
    decrypt(this.files[0]);
  },
  false
);

const metadataInput = document.getElementById("metadata");
metadataInput.addEventListener(
  "change",
  function(e) {
    e.preventDefault();
    metadata(this.files[0]);
  },
  false
);

const manifestInput = document.getElementById("manifest");
manifestInput.addEventListener(
  "change",
  function(e) {
    e.preventDefault();
    manifest(this.files[0]);
  },
  false
);