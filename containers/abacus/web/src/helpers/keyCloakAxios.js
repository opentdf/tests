/* eslint-disable no-param-reassign */
import axios from 'axios';
import { generateKeycloakAuthHeaders, OIDC_BASE_URL } from '@/helpers/requestClient';

const baseURL = OIDC_BASE_URL;

const keyCloakClient = () => {
  const instance = axios.create({
    baseURL,
  });

  instance.interceptors.request.use((config) => {
    config.headers = {
      ...config.headers,
      ...generateKeycloakAuthHeaders(),
    };

    return config;
  });

  return instance;
};

export default keyCloakClient();
