import axios from 'axios';
import AuthProvider from './provider';
import HttpRequest from './http-request';

import type { AxiosResponse, AxiosRequestConfig } from 'axios';

const { request } = axios;

type AuthorizingFunction = (req: HttpRequest) => Promise<void>;

/**
 * Client for EAS interaction, specifically fetching entity object.
 */
class EAS {
  authProvider: AuthorizingFunction;

  endpoint: string;

  // Required `any` below is to match type from axios library.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  requestFunctor: <T = any, R = AxiosResponse<T>>(config: AxiosRequestConfig) => Promise<R>;

  /**
   * Create an object for accessing an Entity Attribute Service.
   * @param {object} config - options to  configure this EAS accessor
   * @param {AuthProvider|function} config.authProvider - interceptor for `http-request.Request` object manipulation
   * @param {string} config.endpoint - the URI to connect to
   * @param {function} [config.requestFunctor=request] - http request async function object
   */
  constructor({ authProvider, endpoint, requestFunctor }) {
    if (authProvider instanceof AuthProvider) {
      this.authProvider = (r) => authProvider.injectAuth(r);
    } else {
      this.authProvider = authProvider;
    }
    this.endpoint = endpoint;
    this.requestFunctor = requestFunctor || request;
  }

  /**
   * Request an entity object for the current user.
   * @param {object} config - options for the request
   * @param {string} config.publicKey - String encoded public key from the keypair to be used with any subsequent requests refering to the returned EO
   * @param {object} [config.etc] - additional parameters to be passed to the EAS entity-object endpoint
   */
  async fetchEntityObject({ publicKey, ...etc }) {
    // Create a skeleton http request for EAS.
    const httpReq = new HttpRequest();
    httpReq.headers['Content-Type'] = 'application/json';

    // Connect the same ref to each name so authProvider can manipulate either.
    // eslint-disable-next-line no-multi-assign
    httpReq.body = httpReq.params = { publicKey, ...etc };
    httpReq.url = this.endpoint;
    httpReq.method = 'post';

    // Delegate modifications to the auth provider.
    // TODO: Handle various exception cases from interface docs.
    await this.authProvider(httpReq);

    // Execute the http request using axios.
    const axiosParams = {
      method: httpReq.method,
      headers: httpReq.headers,
      url: httpReq.url,
      params: undefined,
      data: undefined,
    };
    // Allow the authProvider to change the method.
    if (httpReq.method === 'post' || httpReq.method === 'patch' || httpReq.method === 'put') {
      axiosParams.data = httpReq.body;
    } else {
      axiosParams.params = httpReq.body;
    }
    return (await this.requestFunctor(axiosParams)).data;
  }
}

export default EAS;
