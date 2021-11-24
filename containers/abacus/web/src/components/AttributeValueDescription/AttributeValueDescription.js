import PropTypes from 'prop-types';
// NOTE(PLAT-875): Deleted for demo
// import SshKeyValue from '@/components/SshKeyValue';
import DescriptionTable from '@/components/DescriptionTable';
import { generateTestIds } from '@/helpers';

export const testIds = generateTestIds('attribute_value_description', [
  'descriptionTable',
  'attributeUrl',
  'sshKey',
]);

// NOTE(PLAT-875): Deleted for demo
// eslint-disable-next-line no-unused-vars
function AttributeValueDescription({ attributeUrl, keyAccessUrl, publicKey }) {
  const attributeProps = [
    {
      name: 'Attribute',
      value: (
        <a data-testid={testIds.attributeUrl} href={attributeUrl}>
          {attributeUrl}
        </a>
      ),
    },
  ];
  return (
    <div data-testid={testIds._}>
      <DescriptionTable properties={attributeProps} />
    </div>
  );
}

AttributeValueDescription.propTypes = {
  attributeUrl: PropTypes.string,
  keyAccessUrl: PropTypes.string,
  publicKey: PropTypes.string,
};

AttributeValueDescription.defaultProps = {
  attributeUrl: '',
  keyAccessUrl: '',
  publicKey: '',
};

export default AttributeValueDescription;
