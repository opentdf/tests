import { AxiosInstance, AxiosResponse } from "axios";
import { useEffect, useState } from "react";
import { toast } from "react-toastify";
import { getCancellationConfig } from "../service";

export type Method = 'get' | 'delete' | "put" | 'post';
export type Config = { method: Method, path: string, params?: Record<any, any>; };

export const useFetch = <T>(client: AxiosInstance, config: Config): [T | undefined,] => {
  const [data, setData] = useState<T>();

  useEffect(() => {
    const { token, cancel } = getCancellationConfig();

    client
    [config.method](config.path, {
      cancelToken: token,
      ...config.params
    })
      .then((res) => {
        setData(res.data);
      })
      .catch((error) => toast.error(error));

    return () => {
      cancel("Operation canceled by the user.");
    };
  }, [client, config.method, config.params, config.path]);


  return [data];
};

export const useLazyFetch = <T>(client: AxiosInstance,): [(config: Config) => Promise<AxiosResponse<any, any>>, T | undefined] => {
  const [data, setData] = useState<T>();

  const makeRequest = async (config: Config) => {
    const res = await client[config.method](config.path, config.params);

    setData(res.data);
    return res;
  };

  return [makeRequest, data];
};
