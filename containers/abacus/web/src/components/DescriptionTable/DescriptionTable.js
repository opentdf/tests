import PropTypes from 'prop-types';
import { generateTestIds } from '@/helpers';
import styles from './DescriptionTable.module.css';

export const testIds = generateTestIds('description_table', ['tableBody', 'descriptionItem']);

function DescriptionTable({ properties }) {
  const tableRows = properties.map((prop) => {
    return (
      <tr key={prop.name} data-testid={testIds.descriptionItem}>
        <td className={styles.name}>{prop.name}</td>
        <td>{prop.value}</td>
      </tr>
    );
  });

  return (
    <table className={styles.description} data-testid={testIds._}>
      <tbody data-testid={testIds.tableBody}>{tableRows}</tbody>
    </table>
  );
}

DescriptionTable.propTypes = {
  properties: PropTypes.arrayOf(
    PropTypes.shape({
      name: PropTypes.string,
      value: PropTypes.node,
    })
  ).isRequired,
};

export default DescriptionTable;
