import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Button } from 'virtuoso-design-system';
import AuthorityNamespaceSelector from '@/components/AuthorityNamespaceSelector/AuthorityNamespaceSelector';

import { Select } from '@/components/Virtruoso';
import useNsAttrValMap from '@/hooks/useNsAttrValMap';
import styles from './EntityAttributeAssigner.module.css';
import useFilterEntities from './hooks/useFilterEntities';

export const EntityAttributeAssigner = ({
  isLoading,
  ns,
  rules,
  attributes,
  assign,
  cancel,
  setSelectedNamespace,
  authorityNamespaces,
}) => {
  const [attrArr, setAttrArr] = useState([]);
  const [selectedAttr, setSelectedAttr] = useState(null);
  const [valueArr, setValueArr] = useState([]);
  const [selectedValue, setSelectedValue] = useState(null);
  const [attrAssignedCount, setAttrAssignedCount] = useState(0);
  const [valAssignedCount, setValAssignedCount] = useState(0);

  const map = useNsAttrValMap(attributes)[ns];
  const rulesToAssign = useFilterEntities(map, rules);

  useEffect(() => {
    setSelectedAttr(null);
    setSelectedValue(null);
    setAttrArr(rulesToAssign.map((rule) => ({ value: rule.name, label: rule.name, ...rule })));
  }, [rulesToAssign]);

  useEffect(() => {
    const selectedAttrObj = attrArr.find(({ value }) => value === selectedAttr);
    if (!selectedAttrObj) {
      setValueArr([]);
      setValAssignedCount(0);
    } else {
      setValueArr(selectedAttrObj.order.map((value) => ({ value, label: value })));
      setValAssignedCount(selectedAttrObj.filteredOutCount);
    }
  }, [selectedAttr, attrArr]);

  useEffect(() => {
    setAttrAssignedCount(
      attrArr.reduce((acc, { filteredOutCount }) => acc + Number(!!filteredOutCount), 0)
    );
  }, [attrArr]);

  const assignOnEntity = () => {
    assign({ ns, attr: selectedAttr, val: selectedValue.value });
  };

  return (
    <>
      <div className={styles.wrapper}>
        <div className={styles.selectContainer}>
          <span className={styles.label}>1. Authority Namespace</span>
          <AuthorityNamespaceSelector
            selectedNamespace={ns}
            setSelectedNamespace={setSelectedNamespace}
            authorityNamespaces={authorityNamespaces}
          />
          <div className={styles.counter}>
            {attrAssignedCount ? `${attrAssignedCount} names already assigned.` : null}
          </div>
        </div>
        <div className={styles.selectContainer}>
          <span className={styles.label}>2. Attribute Name</span>
          <Select
            value={selectedAttr ? attrArr.find(({ value }) => value === selectedAttr) : null}
            options={attrArr}
            onChange={({ value }) => {
              setSelectedAttr(value);
              setSelectedValue(null);
            }}
            isDisabled={!attrArr.length}
          />
          <div className={styles.counter}>
            {valAssignedCount ? `${valAssignedCount} values already assigned.` : null}
          </div>
        </div>
        <div className={styles.selectContainer}>
          <span className={styles.label}>3. Attribute Value</span>
          <Select
            value={selectedValue}
            options={valueArr}
            onChange={(val) => {
              setSelectedValue(val);
            }}
            isDisabled={!valueArr.length}
          />
        </div>
      </div>

      <div className={styles.buttonWrapper}>
        {isLoading ? (
          <Button variant={Button.VARIANT.PRIMARY} size={Button.SIZE.MEDIUM} disabled>
            Saving...
          </Button>
        ) : (
          <>
            <Button variant={Button.VARIANT.SECONDARY} size={Button.SIZE.MEDIUM} onClick={cancel}>
              Cancel
            </Button>
            <div className={styles.buttonBrake} />
            <Button
              variant={Button.VARIANT.PRIMARY}
              size={Button.SIZE.MEDIUM}
              onClick={assignOnEntity}
              disabled={!selectedAttr || !selectedValue}
            >
              Assign to Entity
            </Button>
          </>
        )}
      </div>
    </>
  );
};

EntityAttributeAssigner.propTypes = {
  isLoading: PropTypes.bool,
  ns: PropTypes.string,
  // eslint-disable-next-line react/forbid-prop-types
  rules: PropTypes.array,
  // eslint-disable-next-line react/forbid-prop-types
  authorityNamespaces: PropTypes.array,
  attributes: PropTypes.arrayOf(PropTypes.string),
  setSelectedNamespace: PropTypes.func,
  assign: PropTypes.func,
  cancel: PropTypes.func,
};

EntityAttributeAssigner.defaultProps = {
  isLoading: false,
  ns: '',
  rules: [],
  authorityNamespaces: [],
  attributes: [],
  setSelectedNamespace: () => {},
  assign: () => {},
  cancel: () => {},
};

export default EntityAttributeAssigner;
