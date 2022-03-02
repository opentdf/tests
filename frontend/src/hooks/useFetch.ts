import { AxiosInstance, AxiosResponse, AxiosError, AxiosResponseHeaders } from "axios";
import { useCallback, useEffect, useState } from "react";
import { toast } from "react-toastify";
import { getCancellationConfig } from "../service";

export type Method = 'get' | 'delete' | "put" | 'post';
export type Config = { method: Method, path: string, params?: Record<any, any>; data?: Record<any, any>; };

function isAxiosError(error: any): error is AxiosError {
  return (error as AxiosError).isAxiosError !== undefined;
}

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

export const useLazyFetch = <T>(client: AxiosInstance): [<Q>(config: Config) => Promise<AxiosResponse<Q, any>>, { loading: boolean, data: T | undefined, headers: AxiosResponseHeaders | undefined }] => {
  const [data, setData] = useState<T>();
  const [headers, setHeaders] = useState<AxiosResponseHeaders>();
  const [loading, setLoading] = useState(false);

  const makeRequest = useCallback(async (config: Config) => {
    setLoading(true);

    const methods = {
      get: () => client.get(config.path, { params: config.params }),
      post: () => client.post(config.path, config.data, config.params),
      put: () => client.put(config.path, config.data),
      delete: () => client.delete(config.path, config.params)
    };

    try {
      const res = await methods[config.method]();
      setHeaders(res.headers);
      setData(res.data);
      return res;
    } catch (error) {
      if (isAxiosError(error) && error.response) {
        toast.error(error.message);
        return error.response;
      } else {
        throw new Error(error as string);
      }
    } finally {
      setLoading(false);
    }
  }, [client]);

  return [makeRequest, { loading, data, headers }];
};
