import PropTypes from 'prop-types';

export const TYPE_NPE = 'NPE';
export const TYPE_PERSON = 'Person';

class Entity {
  constructor(entity) {
    this.props = { ...entity };
  }

  get name() {
    return this.props.name || 'N/A';
  }

  get email() {
    return this.props.email || 'N/A';
  }

  get type() {
    return this.props.nonPersonEntity ? TYPE_NPE : TYPE_PERSON;
  }

  get userId() {
    return this.props.userId;
  }

  get attributes() {
    return this.props.attributes;
  }

  hasAttribute(namespace, name, value) {
    if (Array.isArray(this.props.attributes)) {
      return this.props.attributes.some(
        (attrUri) => attrUri === `${namespace}/attr/${name}/value/${value}`
      );
    }
    return false;
  }
}

export const propTypes = {
  name: PropTypes.string.isRequired,
  email: PropTypes.string.isRequired,
  type: PropTypes.string.isRequired,
  userId: PropTypes.string.isRequired,
};

export default Entity;
