import React from 'react';
import { render, screen } from '@testing-library/react';
import SshKeyValue, { testIds } from './SshKeyValue';

const sshKey =
  'AAAAB3NzaC1yc2EAAAADAQABAAABAQDDgnYPRRJnuGexDiy2mLsMDoXAJdqWwhDQyCV4R5bfXSfzJJXUrn0O2nt/wGyYuQq6k1LnKmdmY5eZPRXMxnyTf4ZfjkuIf36XEateRxlO63kKc5xPD9wTgJqNl+IjKUNg0bkznKjWsXvEFqjy76/F6hgpuC+8/6ngS9KWOGfHO5XXEA0mu614c8ENfmtlnB4LdaPpyXolTmTPkaLX+7C0KfmZSOsyOsEnWSspjoqa8R4huQBlvXgVBXAMjVic33A3+8P3R4KBOSGq2RU/8m2jM0WtW9zj9a3LXRnJXneSVbOaK9TtfaDW3zQ/C8alaMrWzBLXfXRdLvCEA5w4dSyj';

describe('<SshKeyValue />', () => {
  it('should render component', () => {
    const { getByTestId } = render(<SshKeyValue sshKey={sshKey} />);
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByTestId(testIds.keyValue)).toBeInTheDocument();
    // expect(getByTestId(testIds.infoIcon)).toBeInTheDocument(); // https://github.com/jsdom/jsdom/issues/300
    expect(screen.queryByText(sshKey)).toBeInTheDocument();
  });
});
