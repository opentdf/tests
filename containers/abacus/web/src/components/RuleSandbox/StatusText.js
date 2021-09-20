import React from 'react';
import PropTypes from 'prop-types';

export const TEXT_SELECT_VALUES = 'Select data & entity attributes to test access.';
export const TEXT_SELECT_ENTITY = 'Select an entity attribute to test access.';
export const TEXT_SELECT_DATA = 'Select a data attribute to test access.';

const checkData = (data, key) =>
  Array.isArray(data[key]) ? !data[key].every((item) => item === false) : data[key] > -1;

function StatusText({ access, data }) {
  const isData = checkData(data, 'data');
  const isEntity = checkData(data, 'entity');

  if (!isData && !isEntity) {
    return (
      <div>
        <span>{TEXT_SELECT_VALUES}</span>
      </div>
    );
  }

  if (!isData || !isEntity) {
    return (
      <div>
        <span>{!isData ? TEXT_SELECT_DATA : TEXT_SELECT_ENTITY}</span>
      </div>
    );
  }

  return (
    <div>
      <>{'then access would be '}</>
      <span>
        <b>{access ? 'Granted' : 'Denied'}</b>
      </span>
    </div>
  );
}

StatusText.propTypes = {
  access: PropTypes.bool,
  data: PropTypes.shape({
    entity: PropTypes.oneOfType([PropTypes.arrayOf(PropTypes.bool), PropTypes.number]),
    data: PropTypes.oneOfType([PropTypes.arrayOf(PropTypes.bool), PropTypes.number]),
  }),
};
StatusText.defaultProps = {
  access: false,
  data: '',
};
export default StatusText;
