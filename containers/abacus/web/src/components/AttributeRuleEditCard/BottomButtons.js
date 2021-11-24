import { useCallback } from 'react';
import { useRouter } from 'next/router';
import PropTypes from 'prop-types';
import { Button } from '@/components/Virtruoso';
import styles from './AttributeRileEditCard.module.css';

function BottomButtons({ requestUpdateAttribute }) {
  const router = useRouter();
  const cancelAction = useCallback(() => {
    router.push('/attributes');
  }, [router]);
  const saveAction = useCallback(() => {
    requestUpdateAttribute();
    cancelAction();
  }, [cancelAction, requestUpdateAttribute]);

  return (
    <div className={styles.buttonContainer}>
      <div className={styles.btnCancel}>
        <Button
          fullWidth
          variant={Button.VARIANT.SECONDARY}
          size={Button.SIZE.MEDIUM}
          onClick={cancelAction}
        >
          Cancel
        </Button>
      </div>
      <div className={styles.btnSave}>
        <Button
          fullWidth
          variant={Button.VARIANT.PRIMARY}
          size={Button.SIZE.MEDIUM}
          onClick={saveAction}
        >
          Save Rule
        </Button>
      </div>
    </div>
  );
}

BottomButtons.propTypes = {
  requestUpdateAttribute: PropTypes.func.isRequired,
};

export default BottomButtons;
