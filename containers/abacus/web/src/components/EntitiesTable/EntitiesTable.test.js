import React from 'react';
import { render } from '@testing-library/react';
import useNewEntity, { EntityContext } from '@/hooks/useNewEntity';
import EntitiesTable, { testIds } from './EntitiesTable';

function renderComponent(props) {
  const TestEntitiesTable = () => {
    const entityProviderValue = useNewEntity();
    return (
      <EntityContext.Provider value={entityProviderValue}>
        <EntitiesTable {...props} />
      </EntityContext.Provider>
    );
  };
  return render(<TestEntitiesTable />);
}

jest.mock('use-reducer-async');

describe('<EntitiesTable />', () => {
  it('should render a table', () => {
    const { getByTestId } = renderComponent();
    expect(getByTestId(testIds._)).toBeInTheDocument();
  });

  it('should render some data', () => {
    const { getByTestId, getByText } = renderComponent();
    expect(getByTestId(testIds._)).toBeInTheDocument();

    expect(getByText('Bob McBobertson')).toBeInTheDocument();
  });
});
