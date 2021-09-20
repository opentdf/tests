import React from 'react';
import { render } from '@testing-library/react';
import AttributeEntityAssigner, { testIds } from './AttributeEntityAssigner';
import useSearchEntities from './hooks/useSearchEntities';
import EntityRow from './components/EntityRow';

jest.mock('./hooks/useSearchEntities');
jest.mock('./components/EntityRow');

describe('<AttributeEntityAssigner />', () => {
  const attributeName = 'attributeName';
  const attributeValue = 'attributeValue';
  const namespace = 'namespace';

  it('should render search without table', () => {
    useSearchEntities.mockReturnValue({});

    const { getByTestId, queryByTestId } = render(
      <AttributeEntityAssigner
        attributeName={attributeName}
        attributeValue={attributeValue}
        namespace={namespace}
      />
    );
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByTestId(testIds.search)).toBeInTheDocument();
    expect(queryByTestId(testIds.table)).not.toBeInTheDocument();
    expect(queryByTestId(testIds.tableLabel)).not.toBeInTheDocument();
  });

  it('should render table', () => {
    const entities = [{ userId: 1 }, { userId: 2 }];
    useSearchEntities.mockReturnValue({
      entities,
    });

    EntityRow.mockReturnValue(
      <tr>
        <td>entity</td>
      </tr>
    );

    const { getByTestId } = render(
      <AttributeEntityAssigner
        attributeName={attributeName}
        attributeValue={attributeValue}
        namespace={namespace}
      />
    );
    expect(getByTestId(testIds.tableLabel)).toHaveTextContent(
      new RegExp(`Found ${entities.length} entities`)
    );
  });
});
