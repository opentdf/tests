import React from 'react';
import Select from './AuthorityNamespaceSelector';
import Wrap from './AuthorityNamespaceSelectorWrap';

export default (props) => (
  <Wrap>
    {/* eslint-disable-next-line react/jsx-props-no-spreading */}
    <Select {...props} />
  </Wrap>
);
