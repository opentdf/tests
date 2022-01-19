import axios from 'axios';

const baseURL = process.env.REACT_APP_KEYCLOAK_HOST;

const keyCloakClient = () => {
  const instance = axios.create({
    baseURL,
  });

  instance.interceptors.request.use((config) => {
    const token = window.sessionStorage.getItem('keycloak');

    config.headers = {
      ...config.headers,
      authorization: `Bearer ${token}`,
      accept: 'application/json'
    };

    return config;
  });

  return instance;
};

export default keyCloakClient();
