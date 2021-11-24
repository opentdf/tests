import { render, waitFor } from '@testing-library/react';
import * as nextRouter from 'next/router';
import useNewEntity, { EntityContext } from '@/hooks/useNewEntity';

import AttributesNamesPage from '@/pages/attributes/[ns]/attr/[attrName]/value/[attrValue]';

nextRouter.useRouter = jest.fn();

const ns = 'namespace';
const attrName = 'attributeFooBar';
const attrValue = 'attributeFooBarValue';

nextRouter.useRouter.mockImplementation(() => ({
  query: { ns, attrName, attrValue },
  prefetch: jest.fn(() => Promise.resolve()),
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

  it.skip('should render Entities and breadcrumbs from routes used', async () => {
    const { getByText } = render(<TestAttributesComponent />);

    await waitFor(() => {
      expect(getByText(attrName)).toBeTruthy();
      expect(getByText(attrValue)).toBeTruthy();
    });
  });
});
