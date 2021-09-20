require(["nano"], function(nanoESM) {
  const NanoTDFClient = nanoESM.default;
  async function decrypt(file) {
    const config = {
      userId: window.creds.userId,
      entityObjectEndpoint: window.creds.entityObjectEndpoint.substring(
        0,
        window.creds.entityObjectEndpoint.length - "/v1/entity_object".length
      )
    };
    console.log("decrypt: config", config);
    const nano = new NanoTDFClient(config.entityObjectEndpoint, config.userId);
    console.log("decrypt: loading file", nano);
    const fileAb = await file.arrayBuffer();
    console.log("decrypt: keygened", fileAb);
    const decrypted = await nano.decrypt(fileAb);
    console.log("decrypt: decrypted", decrypted);
    const b64encoded = btoa(new TextDecoder().decode(decrypted));
    const a = document.getElementById("download_link_decrypted");
    a.href = `data:application/octet-stream;charset=utf-8;base64,${b64encoded}`;
    a.download = window.creds.dstFile.split("/").pop();
    a.click();
    console.log("decrypt: clicky clicked");
  }

  console.log("decrypt: configure");
  const decryptEl = document.getElementById("decrypt");
  if (decryptEl?.files.length) {
    console.log("decrypt: now");
    decrypt(decryptEl.files[0]).then(() => console.log("decrypt: done!"));
  }
  decryptEl.addEventListener(
    "change",
    async e => {
      console.log("decrypt: handler", e);
      e.preventDefault();
      await decrypt(decryptEl.files[0]);
    },
    false
  );
  console.log("decrypt: registered_ handler");
});
console.log("decrypt: module loaded");
