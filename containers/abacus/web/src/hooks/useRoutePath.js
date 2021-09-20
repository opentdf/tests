import { useRouter } from 'next/router';
import { attrPath } from '@/helpers/routeHelper';

function routerPush(router) {
  return (path, append) =>
    router.push(`${path}${append ? `/${append}` : ''}`, undefined, { shallow: true });
}

export default function useRoutePath() {
  const router = useRouter();
  const { ns, attrName, attrValue } = router.query;
  const push = routerPush(router);

  // Encode namespace since its in the form of `https://example.xyz`
  let nextNs = ns;
  if (ns && typeof ns === 'string') {
    nextNs = encodeURIComponent(ns);
  }

  const paths = {
    attribute: {
      get ns() {
        return attrPath(nextNs);
      },
      get attr() {
        return attrPath(nextNs, attrName);
      },
      get value() {
        return attrPath(nextNs, attrName, attrValue);
      },
    },
  };

  return {
    paths,
    pushAttributeNamespace: (append) => {
      push(paths.attribute.ns, append);
    },
    pushAttributeName: (append) => {
      push(paths.attribute.attr, append);
    },
    pushAttributeValue: (append) => {
      push(paths.attribute.value, append);
    },
  };
}
