import PropTypes from 'prop-types';
import SshKeyValue from '@/components/SshKeyValue';
import DescriptionTable from '@/components/DescriptionTable';

function EntityValueDescription({ email, name, userId }) {
  const attributeProps = [
    {
      name: 'Distinguished Name',
      value: <SshKeyValue sshKey={userId} isCopyToMode />,
    },
    {
      name: 'Common Name',
      value: <b>{name}</b>,
    },
    {
      name: 'Email',
      value: <a href={`mailto:${email}`}>{email}</a>,
    },
  ];
  return (
    <div>
      <DescriptionTable properties={attributeProps} />
    </div>
  );
}

EntityValueDescription.propTypes = {
  email: PropTypes.string,
  name: PropTypes.string,
  userId: PropTypes.string,
};

EntityValueDescription.defaultProps = {
  email: '',
  name: '',
  userId: '',
};

export default EntityValueDescription;
