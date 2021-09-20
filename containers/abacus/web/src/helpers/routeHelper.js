export const ATTR_BASE_PATH = '/attributes';
export const ATTR_NAME_PREFIX = 'attr';
export const ATTR_VALUE_PREFIX = 'value';
export const ENTITY_BASE_PATH = '/entity';

export function attrPath(ns, attrName, attrValue) {
  const paths = [ATTR_BASE_PATH];

  if (ns) {
    paths.push(ns);
    if (attrName && typeof attrName === 'string') {
      paths.push(ATTR_NAME_PREFIX);
      paths.push(attrName);
      if (attrValue && typeof attrValue === 'string') {
        paths.push(ATTR_VALUE_PREFIX);
        paths.push(attrValue);
      }
    }
  }

  return paths.join('/');
}

export function entityPath(entityId) {
  const paths = [ENTITY_BASE_PATH];

  if (entityId) {
    paths.push(entityId);
  }

  return paths.join('/');
}
