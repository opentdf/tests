import axios from "axios";

export const getCancellationConfig = () => {
  const CancelToken = axios.CancelToken;
  const { token, cancel } = CancelToken.source();

  return { token, cancel };
};
