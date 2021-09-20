import React from 'react';
import { render, screen } from '@testing-library/react';

import HomePage from '@/pages/index';

describe('<HomePage />', () => {
  it('should render a layout', async () => {
    render(<HomePage />);

    expect(screen.queryByText(/Content here/)).toBeInTheDocument();
  });
});
