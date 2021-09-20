import React from 'react';
import PropTypes from 'prop-types';
import { Modal, Button } from '@/components/Virtruoso';
import { generateTestIds } from '@/helpers';

export const testIds = generateTestIds('remove_confirmation_modal', [
  'cancelButton',
  'removeButton',
]);

const footer = ({ onCancel, onRemove, loading }) => (
  <>
    {!loading && (
      <Button
        size={Button.SIZE.MEDIUM}
        variant={Button.VARIANT.SECONDARY}
        onClick={onCancel}
        data-testid={testIds.cancelButton}
      >
        Cancel
      </Button>
    )}
    <Button
      size={Button.SIZE.MEDIUM}
      variant={Button.VARIANT.PRIMARY}
      onClick={onRemove}
      danger
      disabled={loading}
      data-testid={testIds.removeButton}
    >
      {loading ? 'Removing...' : 'Remove'}
    </Button>
  </>
);

function RemoveConfirmationModal({ title, children, onCancel, onRemove, loading }) {
  return (
    <Modal
      title={title}
      variant={Modal.VARIANT.SMALL}
      headerTheme={Modal.HEADER_THEME.DARK}
      footer={footer({ onCancel, onRemove, loading })}
      titleIcon={Modal.TITLE_ICON.INFO}
      data-testid={testIds._}
    >
      {children}
    </Modal>
  );
}

RemoveConfirmationModal.propTypes = {
  title: PropTypes.string.isRequired,
  onCancel: PropTypes.func.isRequired,
  onRemove: PropTypes.func.isRequired,
  loading: PropTypes.bool,
  children: PropTypes.node,
};

RemoveConfirmationModal.defaultProps = {
  children: null,
  loading: false,
};

export default RemoveConfirmationModal;
