import { useState } from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react';
import * as nextRouter from 'next/router';
import { jestFn, useReducerAsync } from 'use-reducer-async';
import EntityDetailsPage from '@/pages/entities/[entityId]';
import { requestAuthorityNamespaces, requestEntities } from '@/__fixtures__/requestData';
import { ACTIONS } from '@/reducers/entitiesReducer';
import { testIds } from '@/components/RemoveConfirmationModal/RemoveConfirmationModal';

jest.mock('@/helpers/requestClient');
nextRouter.useRouter = jest.fn();

nextRouter.useRouter.mockImplementation(() => ({
  query: { entityId: 'CN=bob' },
  prefetch: jest.fn(() => Promise.resolve()),
}));

jest.mock('use-reducer-async');

describe('<EntityDetailsPage />', () => {
  it('should render entities page correct', async () => {
    const { getByText } = render(<EntityDetailsPage />);

    await waitFor(() => {
      expect(getByText('Entity')).toBeInTheDocument();
    });
  });

  it.skip('should render namespace with first namespace as default', async () => {
    const { container } = render(<EntityDetailsPage />);
    await waitFor(() => {
      expect(container.querySelector('.select__single-value')).toHaveTextContent(
        requestAuthorityNamespaces[0]
      );
    });
  });

  it('should fetch entities be triggered on initial load', async () => {
    render(<EntityDetailsPage />);

    await waitFor(() => {
      expect(jestFn).toHaveBeenCalledWith({ type: ACTIONS.FETCH });
    });
  });

  it('should display Loading... state if entity is fetching', async () => {
    const loadingEntity = { ...requestEntities[0], fetching: true };
    useReducerAsync.mockImplementation(() => [[loadingEntity], () => {}]);
    const { getByText } = render(<EntityDetailsPage />);

    await waitFor(() => {
      expect(getByText('Loading...')).toBeInTheDocument();
    });
  });

  it('should show assign entity screen when assign button clicked', async () => {
    const { getByText } = render(<EntityDetailsPage />);

    await act(async () => {
      fireEvent.click(getByText('Assign attribute'));
    });

    expect(getByText('1. Authority Namespace')).toBeInTheDocument();
    expect(getByText('2. Attribute Name')).toBeInTheDocument();
    expect(getByText('3. Attribute Value')).toBeInTheDocument();
  });

  it.skip('should delete entity and restore it', async () => {
    let setEntityGlobal;
    const jestFnLocal = jest.fn();
    useReducerAsync.mockImplementation(() => {
      const [entity, setEntity] = useState([[{ ...requestEntities[0] }], jestFnLocal]);
      setEntityGlobal = setEntity;
      return entity;
    });

    const { getByText, getByTestId, container } = render(<EntityDetailsPage />);

    await waitFor(() => {
      expect(container.querySelector('.deleted-item')).not.toBeInTheDocument();
      expect(getByText('Remove from entity')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(getByText('Remove from entity'));
    });
    expect(getByText('Remove "ClassificationUS:TopSecret" from entity?')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(getByTestId(testIds.removeButton));
    });

    expect(jestFnLocal).toHaveBeenLastCalledWith({
      attributeURI: 'https://etheria.local/attr/ClassificationUS/value/TopSecret',
      entityId: 'CN=bob',
      type: ACTIONS.DELETE,
    });

    // emulating deletion progress
    await act(async () => {
      setEntityGlobal([[{ ...requestEntities[0], loading: true }], jestFnLocal]);
    });
    await act(async () => {
      setEntityGlobal([[{ ...requestEntities[0], loading: false }], jestFnLocal]);
    });

    expect(container.querySelector('.deleted-item')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(getByText('Restore'));
    });

    await waitFor(() => {
      expect(jestFnLocal).toHaveBeenLastCalledWith({
        attributeURI: 'https://etheria.local/attr/ClassificationUS/value/TopSecret',
        entityId: 'CN=bob',
        type: ACTIONS.ASSIGN,
      });
    });

    // emulating assign progress
    await act(async () => {
      setEntityGlobal([[{ ...requestEntities[0], loading: true }], jestFnLocal]);
    });
    await act(async () => {
      setEntityGlobal([[{ ...requestEntities[0], loading: false }], jestFnLocal]);
    });

    // attribute restored, cta is about removing it again
    expect(container.querySelector('.deleted-item')).not.toBeInTheDocument();
    expect(getByText('Remove from entity')).toBeInTheDocument();
  });
});
