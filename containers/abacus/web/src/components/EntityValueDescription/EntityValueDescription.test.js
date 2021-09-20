import React from 'react';
import { render } from '@testing-library/react';
import EntityValueDescription from './EntityValueDescription';

const email = 'google@gmail.com';
const userId = 'userId';
const name = 'name';

describe('<EntityValueDescription />', () => {
  it('should render component', () => {
    const { getByText } = render(
      <EntityValueDescription email={email} userId={userId} name={name} />
    );
    expect(getByText(email)).toBeInTheDocument();
    expect(getByText(userId)).toBeInTheDocument();
    expect(getByText(name)).toBeInTheDocument();
  });
});
