import React from 'react';
import { render, waitFor } from '@testing-library/react';
import useNewEntity, { EntityContext } from '@/hooks/useNewEntity';
import { testIds as entitiesTableTestIds } from '@/components/EntitiesTable/EntitiesTable';

import EntitiesPage from '@/pages/entities';

jest.mock('@/helpers/requestClient');

describe('<EntitiesPage />', () => {
  const TestEntitiesPage = () => {
    const entityProviderValue = useNewEntity();
    return (
      <EntityContext.Provider value={entityProviderValue}>
        <EntitiesPage />
      </EntityContext.Provider>
    );
  };
  it('should render entities page', async () => {
    const { getByTestId, getByText } = render(<TestEntitiesPage />);

    await waitFor(() => {
      expect(getByText('Entities', { selector: 'li' })).toBeInTheDocument();
      // NOTE(PLAT-875): Deleted for demo
      // expect(getByText('New Entity')).toBeInTheDocument();
      expect(getByTestId(entitiesTableTestIds._)).toBeInTheDocument();
    });
  });
});
