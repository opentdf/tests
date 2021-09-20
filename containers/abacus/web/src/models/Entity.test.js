import { requestEntities } from '@/__fixtures__/requestData';
import Entity, { TYPE_NPE, TYPE_PERSON } from './Entity';

const expectedPersonEntity = requestEntities[0];
const expectedNonPersonEntity = requestEntities[1];

describe('Entity model', () => {
  it('should take in a person entity item', () => {
    const entity = new Entity(expectedPersonEntity);
    expect(entity.name).toEqual(expectedPersonEntity.name);
    expect(entity.email).toEqual(expectedPersonEntity.email);
    expect(entity.type).toEqual(TYPE_PERSON);
    expect(entity.userId).toEqual(expectedPersonEntity.userId);
  });

  it('should take in a entity item', () => {
    const entity = new Entity(expectedNonPersonEntity);
    expect(entity.name).toEqual('N/A');
    expect(entity.email).toEqual('N/A');
    expect(entity.type).toEqual(TYPE_NPE);
    expect(entity.userId).toEqual(expectedNonPersonEntity.userId);
  });

  it('should determine attribute status', () => {
    const entity = new Entity(expectedPersonEntity);
    const [ns, attrName, attrValue] = expectedPersonEntity.attributes[0]
      .replace(/(https?:\/\/[^/]+)\/attr\/([^/]+)\/value\/([^/]+)/, '$1,$2,$3')
      .split(',');
    expect(entity.hasAttribute(ns, attrName, attrValue)).toEqual(true);
    expect(entity.email).toEqual(expectedPersonEntity.email);
    expect(entity.type).toEqual(TYPE_PERSON);
    expect(entity.userId).toEqual(expectedPersonEntity.userId);
  });
});
