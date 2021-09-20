import React from 'react';
import Container from '@/helpers/storybookContainer';
import RemoveConfirmationModal from './RemoveConfirmationModal';

export default {
  title: 'Remove Confirmation Modal',
  component: RemoveConfirmationModal,
};

export const CommonModal = () => (
  <Container>
    <RemoveConfirmationModal title='Remove attribute from "Full Name"'>
      Lorem ipsum dolor sit amet, consectetur adipiscing elit. Duis egestas venenatis tellus.
    </RemoveConfirmationModal>
  </Container>
);
