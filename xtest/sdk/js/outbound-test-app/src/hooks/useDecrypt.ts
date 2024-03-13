import {useCallback} from "react";
import {Client} from '@opentdf/client';
import {base64ToUint8Arr, getConfig} from '../utils';

export default (keycloak: any) => {
    const CLIENT_CONFIG = getConfig(keycloak);

    return useCallback(async (input: any) => {
        const client = new Client.Client(CLIENT_CONFIG);
        const { buffer } = base64ToUint8Arr(input);
        const decryptParams = new Client.DecryptParamsBuilder()
            .withArrayBufferSource(buffer)
            .build();

        const decryptedStream = await client.decrypt(decryptParams);
        return await decryptedStream.toString();
    }, [CLIENT_CONFIG]);
};