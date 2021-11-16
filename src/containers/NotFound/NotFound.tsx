import { Button } from "antd";
import { NavLink } from "react-router-dom";

import { routes } from "../../routes";

const NotFound = () => {
  return (
    <div>
      <h2>NotFound</h2>

      <NavLink to={routes.HOME}>
        <Button size="large">Go home</Button>
      </NavLink>
    </div>
  );
};

export default NotFound;
