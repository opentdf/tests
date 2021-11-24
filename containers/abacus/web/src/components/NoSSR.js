/* NoSSR component to disable NextJS Isomorphic rendering. To use:

import dynamic from 'next/dynamic';
const NoSSR = dynamic(() => import('@/components/NoSSR'), { ssr: false });

.
.
.
// your component:
 return <div>
    <NoSSR />
       ... your contents ...
    </div>


*/
import PropTypes from 'prop-types';
import generateTestIds from '@/helpers/generateTestIds';

const testIds = generateTestIds('nossr');

function NoSSR({ children }) {
  return <div data-testid={testIds._}>{children}</div>;
}

NoSSR.propTypes = {
  children: PropTypes.node.isRequired,
};

export default NoSSR;
