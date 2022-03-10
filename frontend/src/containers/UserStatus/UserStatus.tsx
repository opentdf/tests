import { useKeycloak } from "@react-keycloak/web";
import {Avatar, Button} from "antd";
import {SelectRealm} from "./SelectRealm";

const UserStatus = () => {
  const { keycloak } = useKeycloak();

  return (
    <>
      <SelectRealm/>
      {keycloak.authenticated && (
        <>
          <Avatar size={32}>{keycloak.subject}</Avatar>
          <Button
            onClick={() => keycloak.logout()}
            data-test-id="logout-button"
          >
            Log out
          </Button>
        </>
      )}

      {!keycloak.authenticated && (
        <Button
          type="primary"
          onClick={() => keycloak.login()}
          data-test-id="login-button"
        >
          Log in
        </Button>
      )}
    </>
  );
};

export default UserStatus;
