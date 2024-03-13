type GetConfig = {
    clientId: string,
    realm: any,
    organizationName: string,
    refreshToken: string,
}

export const getConfig = ({ clientId, realm: organizationName, refreshToken }: GetConfig) => ({
    clientId,
    organizationName,
    exchange: 'refresh',
    oidcOrigin: 'http://localhost:65432/auth/realms/tdf',
    refreshToken,
    kasEndpoint: 'http://localhost:65432/api/kas',
})

export const streamToUint8Arr = async (stream: any) => new Uint8Array(await new Response(stream).arrayBuffer());
export const bufferToBase64 = (buffer: any) => window.btoa([...buffer].map(byte => String.fromCharCode(byte)).join(''));
export const base64ToUint8Arr = (name: any) => Uint8Array.from(atob(name).split(''), char => char.charCodeAt(0));