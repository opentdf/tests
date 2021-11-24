import { useCallback, useMemo } from 'react';
import { Table } from 'antd';
import 'antd/dist/antd.css';
import PropTypes from 'prop-types';

const UsersTable = (props) => {
  const { data, loading, onRowClick } = props;

  const columns = useMemo(
    () => [
      { title: 'Username', key: 'username', dataIndex: 'username' },
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

  const title = useCallback(() => 'Users table', []);

  return (
    <Table
      bordered
      columns={columns}
      dataSource={data}
      loading={loading}
      onRow={onRow}
      pagination={false}
      title={title}
    />
  );
};

UsersTable.propTypes = {
  data: PropTypes.node,
  loading: PropTypes.bool,
  onRowClick: PropTypes.func,
};

UsersTable.defaultProps = {
  data: null,
  loading: false,
  onRowClick: () => {},
};

export default UsersTable;
