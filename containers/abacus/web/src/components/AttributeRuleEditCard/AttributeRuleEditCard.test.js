import React from 'react';
import { render, waitFor, getNodeText, act, fireEvent } from '@testing-library/react';
import * as nextRouter from 'next/router';
import { requestAttributes } from '@/__fixtures__/requestData';
import generateClient from '@/helpers/requestClient';
import AttributeRuleEditCard from './AttributeRuleEditCard';

jest.mock('@/helpers/requestClient');
const { mockClient } = generateClient;

const push = jest.fn();
nextRouter.useRouter = () => ({ push });

describe('<AttributeEditCard />', () => {
  const attrName = 'ClassificationUS';
  const attr = requestAttributes.find(({ name }) => name === attrName);

  it('should render order values in list and sandbox', async () => {
    const { getAllByText } = render(
      <AttributeRuleEditCard attr={attrName} ns="https://etheria.local" />
    );
    await waitFor(() => {
      const { order } = attr;
      order.forEach((name) => {
        // one in list and two in sandbox
        expect(getAllByText(name)).toHaveLength(3);
      });
    });
  });

  it('should change sequence of order items if arrows were clicked', async () => {
    const { getAllByTestId } = render(
      <AttributeRuleEditCard attr={attrName} ns="https://etheria.local" />
    );
    const getItemsText = () => getAllByTestId('vds-list_item-content').map(getNodeText);

    const itemsArr = await waitFor(getItemsText);
    expect(itemsArr).toEqual(attr.order);

    // after priority change items on front end doesnt match data from server
    await act(async () => fireEvent.click(getAllByTestId('vds-downArrow')[0]));
    const itemsNewArr = await waitFor(getItemsText);
    expect(itemsNewArr).not.toEqual(attr.order);

    // items are the same, just sequence were changed
    expect(itemsNewArr.sort()).toEqual(attr.order.sort());
  });

  it('should call redirect on "Cancel" button click', async () => {
    const { getByText } = render(
      <AttributeRuleEditCard attr={attrName} ns="https://etheria.local" />
    );
    await waitFor(() => {
      const cancelButton = getByText('Cancel');

      fireEvent.click(cancelButton);
      expect(push).toHaveBeenCalledTimes(1);
    });
  });

  it('should call client request on "Save Rule" button click', async () => {
    const { getByText } = render(
      <AttributeRuleEditCard attr={attrName} ns="https://etheria.local" />
    );
    await waitFor(() => {
      const saveButton = getByText('Save Rule');
      fireEvent.click(saveButton);

      const clientParam = [{ name: attrName }, attr];
      expect(mockClient.mock.calls[mockClient.mock.calls.length - 1]).toEqual([
        'src.web.attribute_name.update',
        clientParam,
      ]);
    });
  });
});
