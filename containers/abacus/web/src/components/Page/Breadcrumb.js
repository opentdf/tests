import Link from 'next/link';
import PropTypes from 'prop-types';
import clsx from 'clsx';
import styles from './Page.module.css';

function Breadcrumb({ text, href, separator }) {
  // Separator
  if (separator) {
    return <li className={clsx(styles.breadcrumbText, styles.breadcrumbSeparator)}>&gt;</li>;
  }

  // Link breadcrumb
  if (href) {
    return (
      <li className={clsx(styles.breadcrumbText, styles.breadcrumbLink)}>
        <Link shallow href={href}>
          <a>{text}</a>
        </Link>
      </li>
    );
  }

  // Text breadcrumb
  return <li className={clsx(styles.breadcrumbText)}>{text}</li>;
}

Breadcrumb.displayName = 'Breadcrumb';

Breadcrumb.propTypes = {
  text: PropTypes.string,
  href: PropTypes.string,
  separator: PropTypes.bool,
};

Breadcrumb.defaultProps = {
  text: '',
  href: null,
  separator: false,
};

export default Breadcrumb;
