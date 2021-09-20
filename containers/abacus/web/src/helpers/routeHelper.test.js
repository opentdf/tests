import {
  attrPath,
  entityPath,
  ATTR_BASE_PATH,
  ATTR_NAME_PREFIX,
  ATTR_VALUE_PREFIX,
  ENTITY_BASE_PATH,
} from './routeHelper';

test('attrPath', () => {
  const namespace = 'namespace';
  const attrName = 'attrName';
  const attrValue = 'attrValue';
  expect(attrPath()).toEqual(ATTR_BASE_PATH);
  expect(attrPath(null, attrName, attrValue)).toEqual(ATTR_BASE_PATH);
  expect(attrPath(namespace)).toEqual([ATTR_BASE_PATH, namespace].join('/'));
  expect(attrPath(namespace, null, attrValue)).toEqual([ATTR_BASE_PATH, namespace].join('/'));
  expect(attrPath(namespace, attrName)).toEqual(
    [ATTR_BASE_PATH, namespace, ATTR_NAME_PREFIX, attrName].join('/')
  );
  expect(attrPath(namespace, attrName, null)).toEqual(
    [ATTR_BASE_PATH, namespace, ATTR_NAME_PREFIX, attrName].join('/')
  );
  expect(attrPath(namespace, attrName, attrValue)).toEqual(
    [ATTR_BASE_PATH, namespace, ATTR_NAME_PREFIX, attrName, ATTR_VALUE_PREFIX, attrValue].join('/')
  );
});

test('entityPath', () => {
  const entityId = 'entityId';
  expect(entityPath()).toEqual(ENTITY_BASE_PATH);
  expect(entityPath(null)).toEqual(ENTITY_BASE_PATH);
  expect(entityPath(entityId)).toEqual([ENTITY_BASE_PATH, entityId].join('/'));
});
