import { render, screen } from '@testing-library/react';
import DescriptionTable, { testIds } from './DescriptionTable';

const properties = [
  {
    name: 'Prop1',
    value: 'somevalue1',
  },
  {
    name: 'Prop2',
    value: 'somevalue2',
  },
  {
    name: 'Prop3',
    value: 'somevalue3',
  },
];

describe('<DescriptionTable />', () => {
  it('should render component', () => {
    const { getByTestId, getAllByTestId } = render(<DescriptionTable properties={properties} />);
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByTestId(testIds.tableBody)).toBeInTheDocument();
    const descItems = getAllByTestId(testIds.descriptionItem);
    expect(descItems).toHaveLength(3);
    expect(screen.queryByText(properties[0].name)).toBeInTheDocument();
    expect(screen.queryByText(properties[0].value)).toBeInTheDocument();
    expect(screen.queryByText(properties[1].name)).toBeInTheDocument();
    expect(screen.queryByText(properties[1].value)).toBeInTheDocument();
    expect(screen.queryByText(properties[2].name)).toBeInTheDocument();
    expect(screen.queryByText(properties[2].value)).toBeInTheDocument();
  });
});
