// NOTE(PLAT-875): Deleted for demo
// eslint-disable-next-line no-unused-vars
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import AttributeRuleCard, { testIds } from './AttributeRuleCard';

const name = 'name';
const authorityNamespace = 'authorityNamespace';
const values = ['one', 'two'];
const emptyValues = [];
const accessType = 'access-type';
// NOTE(PLAT-875): Deleted for demo
// const newValueLinkText = '+ New Value';
// const detailsLinkText = 'Details';
const editRuleLinkText = 'Edit Rule';

describe('<AttributeRuleCard />', () => {
  it('should render with no attribute values', () => {
    const { getByText, getByTestId } = render(
      <AttributeRuleCard
        name={name}
        authorityNamespace={authorityNamespace}
        values={emptyValues}
        accessType={accessType}
        onDetailsAction={() => {}}
        onNewValueAction={() => {}}
        onEditRuleAction={() => {}}
      />
    );
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByText(name)).toBeInTheDocument();
    expect(screen.queryByText(authorityNamespace)).not.toBeInTheDocument();
    // NOTE(PLAT-875): Deleted for demo
    // expect(getByText(newValueLinkText)).toBeInTheDocument();
    // expect(getByText(detailsLinkText)).toBeInTheDocument();
  });

  it('should render with attribute values', () => {
    const { getAllByText, getByText, getByTestId } = render(
      <AttributeRuleCard
        name={name}
        authorityNamespace={authorityNamespace}
        values={values}
        accessType={accessType}
        onDetailsAction={() => {}}
        onNewValueAction={() => {}}
        onEditRuleAction={() => {}}
      />
    );
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByText(name)).toBeInTheDocument();
    expect(getAllByText(authorityNamespace).length).toEqual(2);
    // NOTE(PLAT-875): Deleted for demo
    // expect(getByText(newValueLinkText)).toBeInTheDocument();
    // expect(getByText(detailsLinkText)).toBeInTheDocument();
  });

  it('should trigger the edit function', async () => {
    const newValueAction = jest.fn();
    const editRuleAction = jest.fn();
    const { getAllByText, getByText, getByTestId } = render(
      <AttributeRuleCard
        name={name}
        authorityNamespace={authorityNamespace}
        values={values}
        accessType={accessType}
        onNewValueAction={(e) => newValueAction(e.preventDefault())}
        onEditRuleAction={(e) => editRuleAction(e.preventDefault())}
      />
    );

    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByText(name)).toBeInTheDocument();
    expect(getAllByText(authorityNamespace).length).toEqual(2);
    // NOTE(PLAT-875): Deleted for demo
    // expect(getByText(detailsLinkText)).toBeInTheDocument();
    expect(getByText(editRuleLinkText)).toBeInTheDocument();
    // expect(getByText(newValueLinkText)).toBeInTheDocument();
    expect(getByTestId(testIds.editRuleAction)).toBeInTheDocument();
    // expect(getByTestId(testIds.newValueAction)).toBeInTheDocument();
    //
    fireEvent.click(getByTestId(testIds.editRuleAction));
    // fireEvent.click(getByTestId(testIds.newValueAction));
    //
    await waitFor(() => expect(editRuleAction).toHaveBeenCalledTimes(1));
    // await waitFor(() => expect(newValueAction).toHaveBeenCalledTimes(1));
  });
});
