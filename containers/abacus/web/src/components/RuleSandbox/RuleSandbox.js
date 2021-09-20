import React, { useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import { generateTestIds } from '@/helpers';
import { iconStyles, File, Users } from '@/icons';
import StatusText from '@/components/RuleSandbox/StatusText';
import styles from './RuleSandbox.module.css';

const RULE_ALL_OF = 'allOf';
const RULE_HIERARCHY = 'hierarchy';
const RULE_ANY_OF = 'anyOf';
const RULES = [RULE_ALL_OF, RULE_ANY_OF, RULE_HIERARCHY];

const INPUT_TYPE_CHECKBOX = 'checkbox';
const INPUT_TYPE_RADIO = 'radio';

const accessGrantedValidators = {
  [RULE_ALL_OF]: ({ entity, data }) => !data.find((val, i) => val && !entity[i]),
  [RULE_ANY_OF]: ({ entity, data }) => data.find((val, i) => val && entity[i]),
  [RULE_HIERARCHY]: ({ entity, data }) => entity <= data,
};

export const testIds = generateTestIds('rule_sandbox', [
  'checkbox',
  `${RULE_HIERARCHY}Rule`,
  `${RULE_ALL_OF}Rule`,
  `${RULE_ANY_OF}Rule`,
  `${INPUT_TYPE_CHECKBOX}Input`,
  `${INPUT_TYPE_RADIO}Input`,
]);

const Checkbox = ({ name, id, onSelected, value, inputType, isChecked }) => (
  <div className={styles.checkboxRow} data-testid={testIds[`${inputType}Input`]}>
    <div className={styles.rowContent}>
      <input type={inputType} checked={isChecked} name={name} id={id} onChange={onSelected} />
      <label htmlFor={id}>{value}</label>
    </div>
  </div>
);

const RuleSandbox = ({ attribute, ...props }) => {
  const [, { rule = RULE_ALL_OF, order = [] }] = Object.entries(attribute)[0];
  const defaultRadio = useMemo(() => ({ entity: -1, data: -1 }), []);
  const defaultCheckbox = useMemo(
    () => ({
      entity: new Array(order.length).fill(false),
      data: new Array(order.length).fill(false),
    }),
    [order.length]
  );

  const [selectedRadio, setSelectedRadio] = useState(defaultRadio);
  const [selectedCheckbox, setSelectedCheckbox] = useState(defaultCheckbox);

  useEffect(() => {
    setSelectedCheckbox({ ...defaultCheckbox });
    setSelectedRadio({ ...defaultRadio });
  }, [attribute, defaultCheckbox, defaultRadio]);

  const selectRadioChange = (key, index) => {
    setSelectedRadio({ ...selectedRadio, [key]: index });
  };

  const selectCheckboxChange = (key, index) => {
    const alteredState = [...selectedCheckbox[key]];
    alteredState[index] = !alteredState[index];
    setSelectedCheckbox({ ...selectedCheckbox, [key]: alteredState });
  };

  const inputType = rule === RULE_HIERARCHY ? INPUT_TYPE_RADIO : INPUT_TYPE_CHECKBOX;
  const onChange = inputType === INPUT_TYPE_RADIO ? selectRadioChange : selectCheckboxChange;
  const dataModel = inputType === INPUT_TYPE_RADIO ? selectedRadio : selectedCheckbox;

  const asInput = (col, value, onSelected, index) => {
    const isChecked =
      inputType === INPUT_TYPE_RADIO
        ? index === selectedRadio[col]
        : !!selectedCheckbox[col][index];
    return (
      <Checkbox
        name={col}
        id={`${col}-${value}`}
        key={`${col}-${value}`}
        onSelected={onSelected}
        inputType={inputType}
        isChecked={isChecked}
        value={value}
      />
    );
  };

  return (
    <div {...props} data-testid={testIds[`${rule}Rule`]} className={styles.mainContainer}>
      <div className={styles.titleHeader}>Rules sandbox</div>
      <div className={styles.sandbox}>
        <form className={styles.sandboxEntries}>
          <fieldset className={styles.dataForm}>
            <legend className={styles.legend}>
              <File className={iconStyles.inline} />
              <span>If data has</span>
            </legend>
            {order.slice(0, 5).map((v, index) =>
              asInput(
                'data',
                v,
                () => {
                  onChange('data', index);
                },
                index
              )
            )}
          </fieldset>
          <fieldset className={styles.entityForm}>
            <legend className={styles.legend}>
              <Users className={iconStyles.inline} />
              <span>and entity has</span>
            </legend>
            {order.map((v, index) =>
              asInput(
                'entity',
                v,
                () => {
                  onChange('entity', index);
                },
                index
              )
            )}
          </fieldset>
        </form>
        <div className={styles.effect}>
          <StatusText data={dataModel} access={accessGrantedValidators[rule](dataModel)} />
        </div>
      </div>
    </div>
  );
};

RuleSandbox.propTypes = {
  attribute: PropTypes.objectOf(
    PropTypes.shape({
      order: PropTypes.arrayOf(PropTypes.string),
      rule: PropTypes.oneOf(RULES),
    })
  ),
};

Checkbox.propTypes = {
  name: PropTypes.string.isRequired,
  isChecked: PropTypes.bool.isRequired,
  id: PropTypes.string.isRequired,
  value: PropTypes.string.isRequired,
  onSelected: PropTypes.func.isRequired,
  inputType: PropTypes.oneOf([INPUT_TYPE_RADIO, INPUT_TYPE_CHECKBOX]).isRequired,
};

RuleSandbox.defaultProps = {
  attribute: { 'https:invalid': { rule: RULE_ALL_OF, order: [] } },
};

export default RuleSandbox;
