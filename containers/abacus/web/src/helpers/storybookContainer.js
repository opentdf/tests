// Disable code coverage. File is for storybook files.
/* istanbul ignore file */
// Disable for storybook convenience helper
/* eslint-disable react/forbid-prop-types */
/* eslint-disable react/jsx-props-no-spreading */
import PropTypes from 'prop-types';
import { Layout } from '@/components/Virtruoso';

function Container({ children, layoutProps, ...props }) {
  return (
    <div {...props}>
      <Layout {...layoutProps}>{children}</Layout>
    </div>
  );
}

Container.propTypes = {
  children: PropTypes.node.isRequired,
  layoutProps: PropTypes.object,
};

Container.defaultProps = {
  layoutProps: {},
};

export default Container;
