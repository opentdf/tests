const serverData = window.SERVER_DATA;
let realm = localStorage.getItem("realm");

if(!serverData.realms.length){
    throw Error("Realm didn't found.");
}

if(!realm) {
    realm = serverData.realms[0];
    localStorage.setItem("realm", serverData.realms[0]);
}

export const keycloakConfig = {
    realm,
    url: serverData.authority,
    clientId: serverData.clientId,
};