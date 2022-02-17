import { useKeycloak } from "@react-keycloak/web";
import { Avatar, Button } from "antd";

const UserStatus = () => {
  const { keycloak } = useKeycloak();

  return (
    <>
      {keycloak.authenticated && (
        <>
          <Avatar size={32}>{keycloak.subject}</Avatar>
          <Button onClick={() => keycloak.logout()}>Log out</Button>
        </>
      )}

      {!keycloak.authenticated && (
        <Button type="primary" onClick={() => keycloak.login()}>
          Log in
        </Button>
      )}
    </>
  );
};

export default UserStatus;
