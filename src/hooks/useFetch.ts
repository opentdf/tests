import { AxiosInstance, AxiosResponse } from "axios";
import { useEffect, useState } from "react";
import { toast } from "react-toastify";
import { getCancellationConfig } from "../service";

export type Method = 'get' | 'delete' | "put" | 'post';
export type Config = { method: Method, path: string, params?: Record<any, any>; data?: Record<any, any>; };

export const useFetch = <T>(client: AxiosInstance, config: Config): [T | undefined,] => {
  const { method, path, params } = config;

  const [data, setData] = useState<T>();

  useEffect(() => {
    const { token, cancel } = getCancellationConfig();

    client[method](path, {
      cancelToken: token,
      ...params
    })
      .then((res) => {
        setData(res.data);
      })
      .catch((error) => toast.error(error));

    return () => {
      cancel("Operation canceled by the user.");
    };
  }, [client, method, params, path]);


  return [data];
};

export const useLazyFetch = <T>(client: AxiosInstance,): [<Q>(config: Config) => Promise<AxiosResponse<Q, any>>, { loading: boolean, data: T | undefined; }] => {
  const [data, setData] = useState<T>();
  const [loading, setLoading] = useState(false);

  const makeRequest = async (config: Config) => {

    setLoading(true);
    const methods = {
      get: () => client.get(config.path, config.params),
      post: () => client.post(config.path, config.data, config.params),
      put: () => client.put(config.path, config.params),
      delete: () => client.delete(config.path, config.params)
    };

    const res = await methods[config.method]();

    setData(res.data);
    setLoading(false);

    return res;
  };

  return [makeRequest, { loading, data }];
};
