import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import StatusText, {
  TEXT_SELECT_DATA,
  TEXT_SELECT_ENTITY,
  TEXT_SELECT_VALUES,
} from '@/components/RuleSandbox/StatusText';
import RuleSandbox, { testIds } from './RuleSandbox';

const authorityNamespace = 'https://kas.virtru.com';

const allOfRule = {
  'https://example.virtru.com/attr/allOf': {
    authorityNamespace,
    order: ['A', 'B', 'C', 'D'],
    rule: 'allOf',
  },
};

const anyOfRule = {
  'https://example.virtru.com/attr/anyOf': {
    authorityNamespace,
    order: ['Ceres', 'Eris', 'Haumea', 'Makemake', 'Pluto'],
    rule: 'anyOf',
  },
};

const hierarchyRule = {
  'https://example.virtru.com/attr/hierarchy': {
    authorityNamespace,
    order: ['TradeSecret', 'Proprietary', 'BusinessSensitive', 'Open'],
    rule: 'hierarchy',
    state: 'active',
  },
};

describe('<RuleSandbox />', () => {
  it('should render a rule sandbox', () => {
    const { getByText } = render(<RuleSandbox />);
    expect(getByText('Rules sandbox')).toBeTruthy();
  });

  it('should render a all of rule sandbox by default', () => {
    const { getByTestId } = render(<RuleSandbox />);
    expect(getByTestId(testIds.allOfRule)).toBeTruthy();
  });

  it('should render a all of rule sandbox as checkbox', () => {
    const [, { order }] = Object.entries(allOfRule)[0];
    const { getByTestId } = render(<RuleSandbox attribute={allOfRule} />);
    expect(getByTestId(testIds.allOfRule)).toBeTruthy();
    order.forEach((name) => {
      // two checkboxes, for data and entity
      expect(screen.getAllByRole('checkbox', { name }).length).toEqual(2);
    });
  });

  it('should render a any of rule sandbox as checkbox', () => {
    const [, { order }] = Object.entries(anyOfRule)[0];
    const { getByTestId } = render(<RuleSandbox attribute={anyOfRule} />);
    expect(getByTestId(testIds.anyOfRule)).toBeTruthy();
    order.forEach((name) => {
      // two checkboxes, for data and entity
      expect(screen.getAllByRole('checkbox', { name }).length).toEqual(2);
    });
  });

  it('should render a hierarchy rule sandbox as radio', () => {
    const [, { order }] = Object.entries(hierarchyRule)[0];
    const { getByTestId } = render(<RuleSandbox attribute={hierarchyRule} />);
    expect(getByTestId(testIds.hierarchyRule)).toBeTruthy();
    order.forEach((name) => {
      // two checkboxes, for data and entity
      expect(screen.getAllByRole('radio', { name }).length).toEqual(2);
    });
  });

  it('should grant access on hierarchy rule only if entity has higher or same priority attribute', () => {
    const [, { order }] = Object.entries(hierarchyRule)[0];
    const { getByText } = render(<RuleSandbox attribute={hierarchyRule} />);
    const [, lowPriorityEntity] = screen.getAllByRole('radio', { name: order[order.length - 1] });
    const [highPriorityData, highPriorityEntity] = screen.getAllByRole('radio', { name: order[0] });
    fireEvent.click(highPriorityData);
    fireEvent.click(lowPriorityEntity);
    expect(getByText('Denied')).toBeInTheDocument();
    fireEvent.click(highPriorityEntity);
    expect(getByText('Granted')).toBeInTheDocument();
  });

  it('should grant access on all of rule only if entity has all data attributes', () => {
    const [, { order }] = Object.entries(allOfRule)[0];
    const { getByText } = render(<RuleSandbox attribute={allOfRule} />);
    const [dData, dEntity] = screen.getAllByRole('checkbox', { name: order[order.length - 1] });
    const [aData, aEntity] = screen.getAllByRole('checkbox', { name: order[0] });
    fireEvent.click(dData);
    fireEvent.click(aData);
    fireEvent.click(dEntity);
    expect(getByText('Denied')).toBeInTheDocument();
    fireEvent.click(aEntity);
    expect(getByText('Granted')).toBeInTheDocument();
  });

  it('should grant access on any of rule if entity has at least one of data attributes', () => {
    const [, { order }] = Object.entries(anyOfRule)[0];
    const { getByText } = render(<RuleSandbox attribute={anyOfRule} />);
    const [ceresData, ceresEntity] = screen.getAllByRole('checkbox', { name: order[0] });
    const [, plutoEntity] = screen.getAllByRole('checkbox', { name: order[order.length - 1] });

    fireEvent.click(ceresData);
    fireEvent.click(plutoEntity);
    expect(getByText('Denied')).toBeInTheDocument();
    fireEvent.click(ceresEntity);
    expect(getByText('Granted')).toBeInTheDocument();
  });
});

describe('<StatusText />', () => {
  it('should render status text when no data and entity selected', () => {
    const data = { entity: -1, data: -1 };
    const { getByText } = render(<StatusText access data={data} />);
    expect(getByText(TEXT_SELECT_VALUES)).toBeTruthy();
  });
  it('should render status text when need to select entity', () => {
    const data = { entity: -1, data: 0 };
    const { getByText } = render(<StatusText access data={data} />);
    expect(getByText(TEXT_SELECT_ENTITY)).toBeTruthy();
  });
  it('should render status text when need to select data', () => {
    const data = { entity: [false, true], data: [false, false] };
    const { getByText } = render(<StatusText access data={data} />);
    expect(getByText(TEXT_SELECT_DATA)).toBeTruthy();
  });
  it('should render Granted status', () => {
    const data = { entity: [false, true], data: [true, false] };
    const { getByText } = render(<StatusText access data={data} />);
    expect(getByText('Granted')).toBeTruthy();
  });
  it('should render Denied status', () => {
    const data = { entity: [false, true], data: [false, true] };
    const { getByText } = render(<StatusText access={false} data={data} />);
    expect(getByText('Denied')).toBeTruthy();
  });
});
