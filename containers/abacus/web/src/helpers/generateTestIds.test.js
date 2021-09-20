import generateTestIds from './generateTestIds';

const namespace = 'some_namespace';
const defaultContainer = '_';

test('should throw error is no namespace', () => {
  expect(() => generateTestIds()).toThrowError();
});

test('should generate container test id', () => {
  expect(generateTestIds(namespace)).toEqual({ [defaultContainer]: namespace });
});

test('should generate test ids', () => {
  expect(generateTestIds(namespace, ['a', 'b'])).toEqual({
    [defaultContainer]: namespace,
    a: `${namespace}-a`,
    b: `${namespace}-b`,
  });
});

test('should generate custom container test id', () => {
  expect(generateTestIds(namespace, [], { containerKey: '$' })).toEqual({ $: namespace });
  expect(generateTestIds(namespace, ['a', 'b'], { containerKey: '$' })).toEqual({
    $: namespace,
    a: `${namespace}-a`,
    b: `${namespace}-b`,
  });
});
