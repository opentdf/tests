import { useCallback } from "react";
import { Client } from '@opentdf/client';
import { getConfig, streamToUint8Arr, bufferToBase64 } from '../utils';

export default (keycloak) => {
    const CLIENT_CONFIG = getConfig(keycloak);

    return useCallback(async (input) => {
        const client = new Client.Client(CLIENT_CONFIG);
        const encryptParams = new Client.EncryptParamsBuilder()
            .withStringSource(input)
            .withOffline()
            .build();

        const { stream } = await client.encrypt(encryptParams);
        const encryptedBuffer = await streamToUint8Arr(stream);
        const base64 = bufferToBase64(encryptedBuffer);

        return base64;
    }, [CLIENT_CONFIG]);
};
