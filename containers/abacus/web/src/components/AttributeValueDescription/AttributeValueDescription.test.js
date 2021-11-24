import { render, screen } from '@testing-library/react';
import AttributeValueDescription, { testIds } from './AttributeValueDescription';

const attributeUrl = 'https://demo.dodiis.mil/attr/Classification+US/value/Top+Secret';
const kasAccessUrl = 'https://kas.domain.tld/';
const publicKey =
  'AAAAB3NzaC1yc2EAAAADAQABAAABAQDDgnYPRRJnuGexDiy2mLsMDoXAJdqWwhDQyCV4R5bfXSfzJJXUrn0O2nt/wGyYuQq6k1LnKmdmY5eZPRXMxnyTf4ZfjkuIf36XEateRxlO63kKc5xPD9wTgJqNl+IjKUNg0bkznKjWsXvEFqjy76/F6hgpuC+8/6ngS9KWOGfHO5XXEA0mu614c8ENfmtlnB4LdaPpyXolTmTPkaLX+7C0KfmZSOsyOsEnWSspjoqa8R4huQBlvXgVBXAMjVic33A3+8P3R4KBOSGq2RU/8m2jM0WtW9zj9a3LXRnJXneSVbOaK9TtfaDW3zQ/C8alaMrWzBLXfXRdLvCEA5w4dSyj';

describe('<AttributeValueDescription />', () => {
  // eslint-disable-next-line jest/no-disabled-tests
  it.skip('should render component', () => {
    const { getByTestId } = render(
      <AttributeValueDescription
        attributeUrl={attributeUrl}
        keyAccessUrl={kasAccessUrl}
        publicKey={publicKey}
      />
    );
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByTestId(testIds.attributeUrl)).toBeInTheDocument();
    expect(screen.queryByText(attributeUrl)).toBeInTheDocument();
    expect(screen.queryByText(kasAccessUrl)).toBeInTheDocument();
    // NOTE(PLAT-875): Deleted for demo
    // expect(screen.queryByText(publicKey)).toBeInTheDocument();
  });
});
