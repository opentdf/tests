import { useState, useEffect } from 'react';
import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';

const client = generateClient(SERVICE_EAS);

export const STATES = {
  LOADING: 'loading',
  SUCCESS: 'success',
  FAILURE: 'failure',
};

/**
 * hook for assigning an entity to an attribute
 * @param {*} namespace namespace of the attribute
 * @param {*} attributeName name of the attribute
 * @param {*} attributeValue attribute value
 * @param {*} options optional argument
 * @param {function | undefined} options.onSuccess function for redirect after successful assign
 */
function useAssignEntityToAttribute(namespace, attributeName, attributeValue, options = {}) {
  const [state, setState] = useState();
  const [entityId, setEntityId] = useState();
  const attributeURI = `${namespace}/attr/${attributeName}/value/${attributeValue}`;

  useEffect(() => {
    async function updateRemote() {
      try {
        // Wait since the client interface doesn't work at this time
        await client['src.web.entity_attribute.add_attribute_to_entity_via_attribute'](
          {
            attributeURI,
          },
          [entityId]
        );
        if (typeof options.onSuccess === 'function') {
          options.onSuccess(entityId);
        }
        setState(STATES.SUCCESS);
      } catch (e) {
        setState(STATES.FAILURE);
      }
    }

    if (attributeURI && entityId) {
      updateRemote();
    }
  }, [state, attributeURI, entityId, options]);

  return { state, setEntityId };
}

export default useAssignEntityToAttribute;
