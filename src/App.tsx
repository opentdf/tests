import {lazy, Suspense, useEffect} from "react";
import {BrowserRouter as Router, Route, Switch} from "react-router-dom";
import {Button, Input, Layout} from "antd";
import {toast, ToastContainer} from "react-toastify";
import {useKeycloak} from "@react-keycloak/web";
import {AuthProviders, NanoTDFClient} from "@opentdf/client";
import {Header} from "./containers";
import {routes} from "./routes";

import "./App.css";
import {RefreshTokenCredentials} from "@opentdf/client/dist/types/src/nanotdf/types/OIDCCredentials";

const Entitlements = lazy(() => import("./containers/Entitlements"));
const Attributes = lazy(() => import("./containers/Attributes"));
const Client = lazy(() => import("./containers/Client"));
const Home = lazy(() => import("./containers/Home"));
const NotFound = lazy(() => import("./containers/NotFound"));
const User = lazy(() => import("./containers/User"));
// @ts-ignore
const {access, clientId, realm, authority} = window.SERVER_DATA;
const plainText = 'Hello, World!';
let cipherText: ArrayBuffer;

export default function App() {
    // keycloak authentication
    const {keycloak, initialized} = useKeycloak();

    // messaging
    async function handleClick() {
        console.log(client);
        // client.addAttribute("https://opentdf.us/attr/IntellectualProperty/value/Open");
        cipherText = await client.encrypt(plainText);
        console.log(cipherText);
        const clearText = await client.decrypt(cipherText);
        console.log(clearText);
    }

    let client: NanoTDFClient;
    useEffect(() => {
        (async () => {
            if (initialized) {
                keycloak.onAuthError = console.log;
                toast.success(keycloak.subject);
                sessionStorage.setItem("keycloak", keycloak.token || "");
                // @ts-ignore
                const {refreshToken} = keycloak;
                if (!client && refreshToken) {
                    const oidcCredentials: RefreshTokenCredentials = {
                        clientId: clientId,
                        exchange: 'refresh',
                        oidcRefreshToken: refreshToken,
                        // remove /auth/
                        oidcOrigin: authority.replace('/auth/',''),
                        organizationName: realm
                    }
                    const authProvider = await AuthProviders.refreshAuthProvider(oidcCredentials);
                    console.log(authProvider);
                    client = new NanoTDFClient(authProvider, access);
                    await client.fetchOIDCToken();
                }
            }
        })()
    }, [initialized, keycloak]);

    return (
        <Router>
            <Layout style={{minHeight: "100vh"}}>
                <Header/>

                <Layout.Content className="layout">
                    <Suspense fallback="Loading...">
                        <Switch>
                            <Route path={routes.ENTITLEMENTS} exact>
                                <Entitlements/>
                            </Route>
                            <Route path={routes.CLIENT} exact>
                                <Client/>
                            </Route>
                            <Route path={routes.USER} exact>
                                <User/>
                            </Route>
                            <Route path={routes.ATTRIBUTES} exact>
                                <Attributes/>
                            </Route>
                            <Route path={routes.HOME} exact>
                                <Home/>
                            </Route>
                            <Route path={routes.CATCH}>
                                <NotFound/>
                            </Route>
                        </Switch>
                    </Suspense>
                    <Input.Group compact>
                        <Input style={{width: 'calc(100% - 200px)'}} defaultValue={plainText}/>
                        <Button type="primary" onClick={() => handleClick()}>Secure Submit</Button>
                    </Input.Group>
                </Layout.Content>
                <ToastContainer position="bottom-center"/>
            </Layout>
        </Router>
    );
}
