import { useEffect, useState } from "react";
import { Divider } from "antd";
import { useParams } from "react-router";
import { getCancellationConfig, keyCloakClient } from "../../service";
import { toast } from "react-toastify";

// @ts-ignore
const {realm} = window.SERVER_DATA;

const User = () => {
  const { id } = useParams<{ id: string }>();

  const [user, setUser] = useState();

  useEffect(() => {
    const { token, cancel } = getCancellationConfig();

    keyCloakClient
      .get(`/admin/realms/${realm}/users/${id}`, { cancelToken: token })
      .then((res) => {
        setUser(res.data);
      })
      .catch((error) => toast.error(error));

    return () => {
      cancel("Operation canceled by the user.");
    };
  }, [id]);

  return (
    <section>
      <h2>User {id}</h2>

      <Divider />

      <pre>{JSON.stringify(user, null, 2)}</pre>
    </section>
  );
};

export default User;
