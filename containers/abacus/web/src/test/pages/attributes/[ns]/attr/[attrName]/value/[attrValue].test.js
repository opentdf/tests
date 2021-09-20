import React from 'react';
import { render, waitFor } from '@testing-library/react';
import useNewEntity, { EntityContext } from '@/hooks/useNewEntity';
import * as nextRouter from 'next/router';

import AttributesNamesPage from '@/pages/attributes/[ns]/attr/[attrName]/value/[attrValue]';

nextRouter.useRouter = jest.fn();

const ns = 'namespace';
const attrName = 'attributeFooBar';
const attrValue = 'attributeFooBarValue';

nextRouter.useRouter.mockImplementation(() => ({
  query: { ns, attrName, attrValue },
}));

describe('<AttributesNamesPage />', () => {
  const TestAttributesComponent = () => {
    const entityProviderValue = useNewEntity();
    return (
      <EntityContext.Provider value={entityProviderValue}>
        <AttributesNamesPage />
      </EntityContext.Provider>
    );
  };
  it('should render Entities and breadcrumbs from routes used', async () => {
    const { getByText } = render(<TestAttributesComponent />);

    await waitFor(() => {
      expect(getByText(attrName)).toBeTruthy();
      expect(getByText(attrValue)).toBeTruthy();
    });
  });
});
