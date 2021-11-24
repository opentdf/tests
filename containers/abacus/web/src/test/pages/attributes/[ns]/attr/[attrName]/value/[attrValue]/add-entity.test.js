import { render, fireEvent, getByText as getByTextWith } from '@testing-library/react';
import mockNextRouter from '@/test/helpers/mockNextRouter';
// NOTE(PLAT-875): Deleted for demo
// import { attrPath } from '@/helpers/routeHelper';
import { testIds as pageTestIds } from '@/components/Page/Page';
import AddEntityPage, {
  testIds,
} from '@/pages/attributes/[ns]/attr/[attrName]/value/[attrValue]/add-entity';

const attrName = 'name';
const attrValue = 'value';
const ns = 'namespace';

describe('<AddEntityPage />', () => {
  let Router;
  beforeEach(() => {
    Router = mockNextRouter({ query: { attrName, attrValue, ns } });
    Router.mock.push.mockReset();
    Router.mock.back.mockReset();
  });

  it('should show render the page', async () => {
    const { getByTestId } = render(<AddEntityPage />);

    expect(getByTextWith(getByTestId(pageTestIds.headerBreadcrumb), attrName)).toBeInTheDocument();
    expect(getByTextWith(getByTestId(pageTestIds.headerBreadcrumb), attrValue)).toBeInTheDocument();
    expect(
      getByTextWith(getByTestId(pageTestIds.contentTitle), new RegExp(`${attrName}:${attrValue}`))
    ).toBeInTheDocument();
    expect(getByTestId(testIds.cancelAction)).toBeInTheDocument();
  });
  // NOTE(PLAT-875): Deleted for demo
  // it('should trigger router push on edit click', async () => {
  //   const { getByTestId } = render(<AddEntityPage />);
  //
  //   fireEvent.click(getByTestId(testIds.editAction));
  //   expect(Router.mock.push).toHaveBeenCalledTimes(1);
  //   expect(Router.mock.push).toHaveBeenCalledWith(
  //     `${attrPath(ns, attrName, attrValue)}/edit`,
  //     undefined,
  //     { shallow: true }
  //   );
  // });
  // NOTE(PLAT-875): Deleted for demo
  // eslint-disable-next-line jest/no-disabled-tests
  it.skip('should trigger router back on cancel', async () => {
    const { getByTestId } = render(<AddEntityPage />);

    fireEvent.click(getByTestId(testIds.cancelAction));
    expect(Router.mock.back).toHaveBeenCalledTimes(1);
  });
});
