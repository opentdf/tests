import { useState, useEffect } from 'react';
import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';
import Entity from '@/models/Entity';

const client = generateClient(SERVICE_EAS);

export const STATES = {
  LOADING: 'loading',
  SUCCESS: 'success',
  FAILURE: 'failure',
};

function useSearchEntities(searchQuery) {
  const [entities, setEntities] = useState(null);
  const [state, setState] = useState(false);

  // Set
  useEffect(() => {
    (async function fetchData() {
      if (!searchQuery) {
        return;
      }
      setState(STATES.LOADING);
      try {
        const { data } = await client['src.web.entity.find']({ q: searchQuery });
        setState(STATES.SUCCESS);
        setEntities(data.map((res) => new Entity(res)));
      } catch (e) {
        setState(STATES.FAILURE);
      }
    })();
  }, [searchQuery]);

  return { entities, state };
}

export default useSearchEntities;
