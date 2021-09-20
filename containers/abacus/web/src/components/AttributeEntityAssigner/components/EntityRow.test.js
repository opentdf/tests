import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import { requestEntities } from '@/__fixtures__/requestData';
import Entity from '@/models/Entity';
import useNewEntity, { EntityContext } from '@/hooks/useNewEntity';
import EntityRow, { testIds } from './EntityRow';
import useAssignEntityToAttribute, { STATES } from '../hooks/useAssignEntityToAttribute';

jest.mock('../hooks/useAssignEntityToAttribute');

// eslint-disable-next-line react/prop-types
const Container = ({ children }) => {
  return (
    <table>
      <tbody>{children}</tbody>
    </table>
  );
};

describe('<EntityRow />', () => {
  const attributeName = 'attributeName';
  const attributeValue = 'attributeValue';
  const namespace = 'namespace';

  beforeEach(() => {
    useAssignEntityToAttribute.mockReset();
  });

  it('should render entity as assign to attribute', () => {
    const entity = new Entity(requestEntities[0]);
    const setEntityId = jest.fn();
    useAssignEntityToAttribute.mockReturnValue({ setEntityId });
    const TestEntityRow = () => {
      const entityProviderValue = useNewEntity();
      return (
        <EntityContext.Provider value={entityProviderValue}>
          <Container>
            <EntityRow
              attributeName={attributeName}
              attributeValue={attributeValue}
              entity={entity}
              namespace={namespace}
            />
          </Container>
        </EntityContext.Provider>
      );
    };
    const { getByTestId } = render(<TestEntityRow />);
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByTestId(testIds.name)).toHaveTextContent(entity.name);
    expect(getByTestId(testIds.email)).toHaveTextContent(entity.email);
    expect(getByTestId(testIds.type)).toHaveTextContent(entity.type);
    expect(getByTestId(testIds.userId)).toHaveTextContent(entity.userId);
    expect(getByTestId(testIds.action)).toHaveTextContent('Assign to Attribute');
  });

  it('should render entity as failure', () => {
    const entity = new Entity(requestEntities[0]);
    const setEntityId = jest.fn();
    useAssignEntityToAttribute.mockReturnValue({ setEntityId });
    const TestEntityRow = () => {
      const entityProviderValue = useNewEntity();
      return (
        <EntityContext.Provider value={entityProviderValue}>
          <Container>
            <EntityRow
              attributeName={attributeName}
              attributeValue={attributeValue}
              entity={entity}
              namespace={namespace}
            />
          </Container>
        </EntityContext.Provider>
      );
    };
    const { getByTestId } = render(<TestEntityRow />);
    expect(getByTestId(testIds.action)).toHaveTextContent('Assign to Attribute');
  });

  it('should render entity as already assigned', () => {
    useAssignEntityToAttribute.mockReturnValue({});
    const entity = new Entity(requestEntities[0]);
    const TestEntityRow = () => {
      const entityProviderValue = useNewEntity();
      return (
        <EntityContext.Provider value={entityProviderValue}>
          <Container>
            <EntityRow
              attributeName="ClassificationUS"
              attributeValue="TopSecret"
              entity={entity}
              namespace="https://etheria.local"
            />
          </Container>
        </EntityContext.Provider>
      );
    };
    const { getByTestId } = render(<TestEntityRow />);

    expect(getByTestId(testIds.action)).toHaveTextContent('Already assigned');
  });

  it('should render entity as saving', () => {
    useAssignEntityToAttribute.mockReturnValue({ setEntityId: () => {}, state: STATES.LOADING });
    const entity = new Entity(requestEntities[0]);
    const TestEntityRow = () => {
      const entityProviderValue = useNewEntity();
      return (
        <EntityContext.Provider value={entityProviderValue}>
          <Container>
            <EntityRow attributeName="x" attributeValue="y" entity={entity} namespace="namespace" />
          </Container>
        </EntityContext.Provider>
      );
    };
    const { getByTestId } = render(<TestEntityRow />);

    expect(getByTestId(testIds.action)).toHaveTextContent('Saving...');
  });

  it('should render entity as assigned', () => {
    useAssignEntityToAttribute.mockReturnValue({ setEntityId: () => {}, state: STATES.SUCCESS });
    const entity = new Entity(requestEntities[0]);
    const TestEntityRow = () => {
      const entityProviderValue = useNewEntity();
      return (
        <EntityContext.Provider value={entityProviderValue}>
          <Container>
            <EntityRow attributeName="x" attributeValue="y" entity={entity} namespace="namespace" />
          </Container>
        </EntityContext.Provider>
      );
    };
    const { getByTestId } = render(<TestEntityRow />);

    expect(getByTestId(testIds.action)).toHaveTextContent('Assigned');
  });

  it('should trigger on assignment', () => {
    const entity = new Entity(requestEntities[0]);
    const setEntityId = jest.fn();
    useAssignEntityToAttribute.mockReturnValue({ setEntityId });
    const TestEntityRow = () => {
      const entityProviderValue = useNewEntity();
      return (
        <EntityContext.Provider value={entityProviderValue}>
          <Container>
            <EntityRow
              attributeName={attributeName}
              attributeValue={attributeValue}
              entity={entity}
              namespace={namespace}
            />
          </Container>
        </EntityContext.Provider>
      );
    };
    const { getByTestId } = render(<TestEntityRow />);
    expect(getByTestId(testIds.action)).toHaveTextContent('Assign to Attribute');

    fireEvent.click(getByTestId(testIds.assignAction));

    expect(setEntityId).toHaveBeenCalledTimes(1);
    expect(setEntityId).toHaveBeenCalledWith(entity.userId);
  });
});
