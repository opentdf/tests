import { useCallback, useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Select } from '@/components/Virtruoso';

function AuthorityNamespaceSelector({
  setSelectedNamespace,
  selectedNamespace,
  authorityNamespaces,
}) {
  const [valLabel, setValLabel] = useState('');
  const [options, setOptions] = useState([]);
  const onChange = useCallback(({ value }) => setSelectedNamespace(value), [setSelectedNamespace]);

  useEffect(() => {
    setValLabel({ label: selectedNamespace, value: selectedNamespace });
  }, [selectedNamespace]);

  useEffect(() => {
    setOptions(authorityNamespaces.map((namespace) => ({ label: namespace, value: namespace })));
    if (!selectedNamespace && authorityNamespaces.length) {
      setSelectedNamespace(authorityNamespaces[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authorityNamespaces, setSelectedNamespace]);

  return (
    <Select
      isLoading={!selectedNamespace}
      value={valLabel}
      options={options}
      isDisabled={authorityNamespaces.length <= 1}
      onChange={onChange}
    />
  );
}

AuthorityNamespaceSelector.propTypes = {
  setSelectedNamespace: PropTypes.func,
  selectedNamespace: PropTypes.string,
  // eslint-disable-next-line react/forbid-prop-types
  authorityNamespaces: PropTypes.array,
};

AuthorityNamespaceSelector.defaultProps = {
  setSelectedNamespace: () => {},
  authorityNamespaces: [],
  selectedNamespace: '',
};

export default AuthorityNamespaceSelector;
