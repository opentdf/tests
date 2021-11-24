import { useEffect } from 'react';
import PropTypes from 'prop-types';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { Heading } from '@/components/Virtruoso';
import { generateTestIds } from '@/helpers';

export const testIds = generateTestIds('redirect', ['heading', 'link']);

export const REDIRECT_MS = 2 * 1000;

function Redirect({ href, as: asHref }) {
  const router = useRouter();
  const message = `Redirecting to ${href}`;

  useEffect(() => {
    const timer = setTimeout(() => router.push(href, asHref || href), REDIRECT_MS);
    return () => {
      clearTimeout(timer);
    };
  });

  return (
    <div>
      <Heading size={Heading.SIZE.SMALL} rank={4}>
        {message}
      </Heading>
      <Link shallow href={href} as={asHref || href}>
        <a data-testid={testIds.link}>Click to redirect now.</a>
      </Link>
    </div>
  );
}

Redirect.propTypes = {
  href: PropTypes.string.isRequired,
  as: PropTypes.string,
};

Redirect.defaultProps = {
  as: null,
};

export default Redirect;
