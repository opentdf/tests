import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';

const easClient = generateClient(SERVICE_EAS);

export default async function handler(req, res) {
  const { probe = 'liveness' } = req.query;
  switch (probe) {
    case 'readiness':
      await easClient.paths['/healthz'].get({ probe: 'liveness' }, null, {
        headers: { 'X-Virtru-Healthz-Client': 'abacus' },
        timeout: 10,
      });
      res.status(204).send('');
      break;
    case 'liveness':
      res.status(200).json({
        buildId: process.env.CONFIG_BUILD_ID || 'dev',
        version: process.env.PKG_VERSION || 'unknown',
      });
      break;
    default:
      res.status(400).json({ error: `Unknown probe type [${probe}]` });
  }
}
