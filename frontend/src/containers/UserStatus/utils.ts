interface ISimpleKeycloak {
    authenticated?: boolean | undefined;
    logout: () => void;
};

export const saveNewRealm = function (keycloak: ISimpleKeycloak, realm: string){
    if (keycloak.authenticated) {
        localStorage.setItem('realm-tmp', realm);
        keycloak.logout();
    } else {
        localStorage.setItem('realm', realm);
        window.document.location.href = "/";
    }
};