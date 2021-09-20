export const requestNoResponse = null;

export const requestAttributes = [
  {
    authorityNamespace: 'https://etheria.local',
    name: 'default',
    order: [''],
    rule: 'allOf',
    state: 'active',
  },
  {
    authorityNamespace: 'https://etheria.local',
    name: 'ClassificationUS',
    order: ['TopSecret', 'Secret', 'CU', 'Unclassified'],
    rule: 'hierarchy',
    state: 'active',
  },
  {
    authorityNamespace: 'https://etheria.local',
    name: 'ClassificationNATO',
    order: ['COSMICTopSecret', 'NATOSecret', 'NATOConfidential', 'NATORestricted'],
    rule: 'hierarchy',
    state: 'inactive',
  },
  {
    authorityNamespace: 'https://etheria.local',
    name: 'SCIControls',
    order: ['SI', 'TK', 'GAMMAZZYY', 'GAMMANEMO'],
    rule: 'allOf',
    state: 'active',
  },
  {
    authorityNamespace: 'https://etheria.local',
    name: 'SensorNTK',
    order: ['UAV-Imagery', 'BFT', 'Sensor-SI', 'Sensor-F', 'SensorImagery'],
    rule: 'anyOf',
    state: 'active',
  },
  {
    authorityNamespace: 'https://etheria.local',
    name: 'Mission',
    order: ['OBJ-MEL', 'OBJ-TOP', 'TF-X', 'TF-99'],
    rule: 'allOf',
    state: 'inactive',
  },
];

export const requestAuthorityNamespaces = [
  'https://etheria.local',
  'http://kas.eas.com',
  'http://kas.example.com',
];

export const requestDefaultAuthorityNamespace = ['https://eas.virtru.com'];

export const requestEntities = [
  {
    name: 'Bob McBobertson',
    email: 'bob@mcbobertson.com',
    userId: 'CN=bob',
    attributes: ['https://etheria.local/attr/ClassificationUS/value/TopSecret'],
  },
  { nonPersonEntity: true, userId: 'CN=bot' },
];

export const apiMethodResponses = {
  // Get attributes
  'src.web.attribute_name.find': (query) => {
    if (query && query.namespace === 'https://etheria.local') {
      return requestAttributes;
    }
    return requestAttributes;
  },
  // Get authority namespaces
  'src.web.authority_namespace.get': (query) => {
    if (query && query.isDefault) {
      return requestDefaultAuthorityNamespace;
    }
    return requestAuthorityNamespaces;
  },
  // Get entities
  'src.web.entity.find': requestEntities,
  'src.web.entity_attribute.get_entities_for_attribute': requestEntities,
  // Assign entity to an attribute
  'src.web.entity_attribute.add_attribute_to_entity_via_attribute': null,
  'src.web.entity_attribute.delete_attribute_from_entity': null,
};

export default {
  requestAttributes,
  requestEntities,
  apiMethodResponses,
};
