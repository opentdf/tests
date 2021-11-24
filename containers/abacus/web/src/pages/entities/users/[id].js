import { useContext, useEffect } from 'react';
import { useRouter } from 'next/router';
import Page from '@/components/Page';
import { KeyCloakContext, KEYCLOAK_ACTIONS } from '@/hooks/useKeyCloak';

const UserPage = () => {
  const router = useRouter();
  const { id } = router.query;

  const [state, sendAction, keyCloak] = useContext(KeyCloakContext);

  useEffect(() => {
    if (keyCloak.authenticated) {
      sendAction({ type: KEYCLOAK_ACTIONS.GET_USER, id });
    }
  }, [id, keyCloak.authenticated, sendAction]);

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      actionAlignment={Page.ACTION_ALIGNMENTS.RIGHT}
      title="Entity"
      description="A person, organization, device, or process who will access data based on their attributes."
    >
      <Page.Breadcrumb text="Entities" />

      <div>
        <h2>{`User ${id}`}</h2>

        <pre>{JSON.stringify(state.user, null, 2)}</pre>
      </div>
    </Page>
  );
};

export default UserPage;
