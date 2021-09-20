import generateClient, { SERVICE_EAS } from './requestClient';

test('should throw error', () => {
  expect(() => generateClient()).toThrowError();
  expect(() => generateClient('blah')).toThrowError();
});

test('should generate EAS client', () => {
  expect(typeof generateClient(SERVICE_EAS)).toEqual('function');
});
