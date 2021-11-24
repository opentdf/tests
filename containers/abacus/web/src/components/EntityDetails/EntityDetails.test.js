import { render } from '@testing-library/react';
import * as nextRouter from 'next/router';
import EntityDetails from './EntityDetails';

jest.mock('@/helpers/requestClient');
nextRouter.useRouter = jest.fn();

nextRouter.useRouter.mockImplementation(() => ({
  query: { entityId: 'foo@barovich' },
}));

describe('<EntityDetails />', () => {
  it('should render component', () => {
    const ns = 'https://eas.eternos.xyz';
    const attributes = [
      'https://eas.eternos.xyz/attr/ClassificationUS/value/Secret',
      'https://eas.eternos.xyz/attr/ClassificationUS/value/Secret1',
      'https://eas.eternos.xyz1/attr/ClassificationUS1/value/Secret2',
    ];
    const { getByText } = render(<EntityDetails attributes={attributes} selectedNamespace={ns} />);
    expect(getByText('Secret')).toBeInTheDocument();
    expect(getByText('Secret1')).toBeInTheDocument();
  });
});
