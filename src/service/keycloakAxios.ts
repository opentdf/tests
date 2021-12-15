import axios from 'axios';

// @ts-ignore
const serverData = window.SERVER_DATA;
const baseURL = serverData.authority;

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
