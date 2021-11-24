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
    const { getByTestId, getByText } = render(<TestEntityRow />);
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByText(entity.name)).toBeTruthy();
    expect(getByText(entity.email)).toBeTruthy();
    expect(getByText(entity.type)).toBeTruthy();
    expect(getByText(entity.userId)).toBeTruthy();
    expect(getByText(entity.email)).toBeTruthy();
    expect(getByText('Assign to Attribute')).toBeTruthy();
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
    const { getByText } = render(<TestEntityRow />);
    expect(getByText('Assign to Attribute')).toBeTruthy();
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
    const { getByText } = render(<TestEntityRow />);

    expect(getByText('Already assigned')).toBeTruthy();
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
    const { getByText } = render(<TestEntityRow />);

    expect(getByText('Saving...')).toBeTruthy();
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
    const { getByText } = render(<TestEntityRow />);

    expect(getByText('Assigned')).toBeTruthy();
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
    const { getByTestId, getByText } = render(<TestEntityRow />);

    expect(getByText('Assign to Attribute')).toBeTruthy();

    fireEvent.click(getByTestId(testIds.assignAction));

    expect(setEntityId).toHaveBeenCalledTimes(1);
    expect(setEntityId).toHaveBeenCalledWith(entity.userId);
  });
});
