import { cleanup, render, getByText as globalGetByText } from '@testing-library/react';

import Card from '.';

afterEach(cleanup);

describe('<Card />', () => {
  it('should render with no header and no content', () => {
    const { getByTestId } = render(<Card />);
    expect(getByTestId('vds-card')).toBeInTheDocument();
  });

  it('should render with no header', () => {
    const { getByTestId, getByText } = render(<Card>Content</Card>);
    expect(getByTestId('vds-card')).toBeInTheDocument();
    expect(getByText('Content')).toBeInTheDocument();
  });

  it('should render with header', () => {
    const { getByTestId } = render(
      <Card>
        <Card.Header id="header" title="Title" />
      </Card>
    );
    expect(getByTestId('vds-card')).toBeInTheDocument();
    expect(getByTestId('vds-card_header')).toBeInTheDocument();
    expect(getByTestId('vds-card_header-title')).toBeInTheDocument();
    expect(globalGetByText(getByTestId('vds-card_header-title'), 'Title')).toBeInTheDocument();
  });

  it('should render with header and subheader', () => {
    const { getByTestId, queryAllByTestId } = render(
      <Card>
        <Card.Header id="header" title="Header" />
        <Card.Header id="subheader" title="SubHeader" />
      </Card>
    );
    const cardHeaders = queryAllByTestId('vds-card_header');
    expect(getByTestId('vds-card')).toBeInTheDocument();
    expect(cardHeaders.length).toEqual(2);
    expect(globalGetByText(cardHeaders[0], 'Header')).toBeInTheDocument();
    expect(globalGetByText(cardHeaders[1], 'SubHeader')).toBeInTheDocument();
  });

  it('should render with header and content', () => {
    const { getByTestId, getByText } = render(
      <Card>
        <Card.Header id="header" title="Header" />
        Content
      </Card>
    );
    expect(getByTestId('vds-card')).toBeInTheDocument();
    expect(getByTestId('vds-card_header')).toBeInTheDocument();
    expect(getByText('Content')).toBeInTheDocument();
  });
});
