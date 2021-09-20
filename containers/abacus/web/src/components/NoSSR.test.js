import React from 'react';
import { render } from '@testing-library/react';
import NoSSR from './NoSSR';

describe('<NoSSR />', () => {
  it('should render component', () => {
    const { container } = render(<NoSSR>test</NoSSR>);
    expect(container).toBeTruthy();
  });
});
