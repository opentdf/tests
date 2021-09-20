import mockNextRouter from '@/test/helpers/mockNextRouter';
import { attrPath } from '@/helpers/routeHelper';
import useRoutePath from './useRoutePath';

jest.mock('@/helpers/routeHelper');

const ns = 'namespace';
const attrName = 'attrName';
const attrValue = 'attrValue';

test('has empty paths when query', () => {
  const value = 'x';

  [{}, { ns }, { ns, attrName }, { ns, attrName, attrValue }].forEach((query) => {
    mockNextRouter({ query });
    const { paths } = useRoutePath();
    attrPath.mockReset();
    attrPath.mockReturnValue(value);
    expect(paths.attribute.ns).toEqual(value);
    expect(attrPath).toHaveBeenCalledTimes(1);
    expect(attrPath).toHaveBeenCalledWith(query.ns);
    expect(paths.attribute.attr).toEqual(value);
    expect(attrPath).toHaveBeenCalledTimes(2);
    expect(attrPath).toHaveBeenCalledWith(query.ns, query.attrName);
    expect(paths.attribute.value).toEqual(value);
    expect(attrPath).toHaveBeenCalledTimes(3);
    expect(attrPath).toHaveBeenCalledWith(query.ns, query.attrName, query.attrValue);
  });
});

test('calls router', () => {
  const value = 'x';
  const appendPath = 'xyz';
  const Router = mockNextRouter();
  const { pushAttributeNamespace, pushAttributeName, pushAttributeValue } = useRoutePath();
  [pushAttributeNamespace, pushAttributeName, pushAttributeValue].forEach((fn) => {
    Router.mock.push.mockClear();
    attrPath.mockReset();
    attrPath.mockReturnValue(value);
    fn();
    expect(Router.mock.push).toHaveBeenCalledTimes(1);
    expect(Router.mock.push).toHaveBeenCalledWith(`${value}`, undefined, {
      shallow: true,
    });
    fn(appendPath);
    expect(Router.mock.push).toHaveBeenCalledTimes(2);
    expect(Router.mock.push).toHaveBeenNthCalledWith(2, `${value}/${appendPath}`, undefined, {
      shallow: true,
    });
  });
});
