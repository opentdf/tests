/* eslint-disable import/no-extraneous-dependencies */
import { withKnobs, text } from '@storybook/addon-knobs';
import Container from '@/helpers/storybookContainer';
import AttributeValueDescription from '.';

export default {
  title: 'Attribute Value Description',
  decorators: [withKnobs],
};

export const SingleCard = () => (
  <Container>
    <AttributeValueDescription
      attributeUrl={text(
        'Attribute URL',
        'https://demo.dodiis.mil/attr/Classification+US/value/Top+Secret'
      )}
      keyAccessUrl={text('KAS URL', 'https://kas.domain.tld/')}
      publicKey={text(
        'Public Key',
        'AAAAB3NzaC1yc2EAAAADAQABAAABAQDDgnYPRRJnuGexDiy2mLsMDoXAJdqWwhDQyCV4R5bfXSfzJJXUrn0O2nt/wGyYuQq6k1LnKmdmY5eZPRXMxnyTf4ZfjkuIf36XEateRxlO63kKc5xPD9wTgJqNl+IjKUNg0bkznKjWsXvEFqjy76/F6hgpuC+8/6ngS9KWOGfHO5XXEA0mu614c8ENfmtlnB4LdaPpyXolTmTPkaLX+7C0KfmZSOsyOsEnWSspjoqa8R4huQBlvXgVBXAMjVic33A3+8P3R4KBOSGq2RU/8m2jM0WtW9zj9a3LXRnJXneSVbOaK9TtfaDW3zQ/C8alaMrWzBLXfXRdLvCEA5w4dSyj'
      )}
    />
  </Container>
);
