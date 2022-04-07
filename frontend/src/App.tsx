import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter as Router, Switch, Route } from "react-router-dom";
import { Layout } from "antd";
import { toast, ToastContainer } from "react-toastify";
import { useKeycloak } from "@react-keycloak/web";

import { Header } from "./containers";
import { routes } from "./routes";

import "./App.css";

import { TargetMode } from "./containers/TargetMode"

const Entitlements = lazy(() => import("./containers/Entitlements"));
const Attributes = lazy(() => import("./containers/Attributes"));
const Client = lazy(() => import("./containers/Client"));
const Home = lazy(() => import("./containers/Home"));
const NotFound = lazy(() => import("./containers/NotFound"));
const User = lazy(() => import("./containers/User"));

export default function App() {
  // keycloak authentication
  const { keycloak, initialized } = useKeycloak();

  keycloak.onAuthError = console.log;

  useEffect(() => {
    if (initialized) {
      toast.success(keycloak.idToken);
      sessionStorage.setItem("keycloak", keycloak.token || "");
      const tmp = localStorage.getItem('realm-tmp');

      if (!keycloak.authenticated && tmp) {
        localStorage.setItem('realm', tmp);
        localStorage.removeItem('realm-tmp');
        window.document.location.href = "/";
      }
    }
  }, [initialized, keycloak]);
  // attributes

  return (
    <Router>
      <Layout style={{ minHeight: "100vh" }}>
        <Header />

        <Layout.Content className="layout">
          <Suspense fallback="Loading...">
            <Switch>
              <Route path={routes.ENTITLEMENTS} exact>
                <Entitlements />
              </Route>
              <Route path={routes.CLIENT} exact>
                <Client />
              </Route>
              <Route path={routes.USER} exact>
                <User />
              </Route>
              <Route path={routes.ATTRIBUTES} exact>
                <Attributes />
              </Route>
              <Route path={routes.HOME} exact>
                <TargetMode />
                <Home />
              </Route>
              <Route path={routes.CATCH}>
                <NotFound />
              </Route>
            </Switch>
          </Suspense>
        </Layout.Content>
        <ToastContainer position="bottom-center" />
      </Layout>
    </Router>
  );
}
