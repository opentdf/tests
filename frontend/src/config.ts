const serverData = window.SERVER_DATA;
let realm = localStorage.getItem("realm");
export const ENV_REALMS = serverData.realms.split(',').filter(item => item !== '');

if(!ENV_REALMS.length){
    throw Error("Realm didn't found.");
}

if(!realm) {
    realm = ENV_REALMS[0];
    localStorage.setItem("realm", realm);
}

export const keycloakConfig = {
    realm,
    url: serverData.authority,
    clientId: serverData.clientId,
};