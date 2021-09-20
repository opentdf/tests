import { createContext, useState } from 'react';

export const EntityContext = createContext({});

function useNewEntity() {
  const [newEntity, setNewEntity] = useState('');

  return { newEntity, setNewEntity };
}

export default useNewEntity;
