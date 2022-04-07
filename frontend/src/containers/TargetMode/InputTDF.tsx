/* istanbul ignore file */
// this file only for test mode
import { Button, Input } from "antd";
import { useEffect } from "react";
import { useKeycloak } from "@react-keycloak/web";
import { toast } from "react-toastify";
import { AUTHORITY, CLIENT_ID, KAS_ENDPOINT, REALM } from "../../config";
const virtru = require("tdf3-js");

// @ts-ignore
const authority = AUTHORITY;
const clientId= CLIENT_ID;
// KAS endpoint
const access = KAS_ENDPOINT;
const realm = REALM;

export const InputTDF = () => {
    const plainText = 'Hello, World!';
    const { keycloak, initialized } = useKeycloak();
    // @ts-ignore
    let client;

    // messaging
    async function handleClick() {
        const encryptParams = new virtru.Client.EncryptParamsBuilder()
            .withStringSource(plainText)
            .withOffline()
            .build();
        // @ts-ignore
        const ct = await client.encrypt(encryptParams);
        const ciphertext = await ct.toString();
        console.log(`ciphered text :${ciphertext}`);

        const decryptParams = new virtru.Client.DecryptParamsBuilder()
            .withStringSource(ciphertext)
            .build();
        // @ts-ignore
        const plaintextStream = await client.decrypt(decryptParams);
        const plaintext = await plaintextStream.toString();
        toast.success(`Text deciphered: ${plainText}`);
        console.log(`deciphered text :${plaintext}`);
    }

    useEffect(() => {
        (async () => {
            if (initialized) {
                const { refreshToken } = keycloak;
                // @ts-ignore
                if (!client && refreshToken) {
                    const token = typeof refreshToken === 'boolean' ? keycloak.token : refreshToken;

                    client = new virtru.Client.Client({
                        clientId,
                        organizationName: realm,
                        oidcRefreshToken: token,
                        kasEndpoint: access,
                        virtruOIDCEndpoint: authority.replace('/auth/', ''),
                    });
                }
            }
        })()
    }, [initialized, keycloak]);

    return (
        <Input.Group compact>
            <Input style={{ width: '50%' }} defaultValue={plainText}/>
            <Button type="primary" id={'encrypt-button'} onClick={() => handleClick()}>Secure Submit</Button>
        </Input.Group>
    );
};