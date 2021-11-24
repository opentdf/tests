import { useCallback, useMemo } from 'react';
import { Table } from 'antd';
import 'antd/dist/antd.css';
import PropTypes from 'prop-types';

const ClientsTable = (props) => {
  const { data, loading, onRowClick } = props;

  const columns = useMemo(
    () => [
      { title: 'Client id', key: 'clientId', dataIndex: 'clientId' },
      { title: 'ID', key: 'id', dataIndex: 'id' },
      {
        title: 'enabled',
        key: 'enabled',
        dataIndex: 'enabled',
        render: (value) => value.toString(),
      },
    ],
    []
  );

  const onRow = useCallback(
    (record) => ({
      onClick: () => onRowClick(record),
    }),
    [onRowClick]
  );

  const title = useCallback(() => 'Clients table', []);

  return (
    <Table
      columns={columns}
      loading={loading}
      title={title}
      onRow={onRow}
      dataSource={data}
      bordered
      pagination={false}
    />
  );
};

ClientsTable.propTypes = {
  data: PropTypes.node,
  loading: PropTypes.bool,
  onRowClick: PropTypes.func,
};

ClientsTable.defaultProps = {
  data: null,
  loading: false,
  onRowClick: () => {},
};

export default ClientsTable;
