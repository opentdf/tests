import { useRouter } from 'next/router';
// NOTE(PLAT-875)
// import { Button } from '@/components/Virtruoso';
import Page from '@/components/Page';
import AttributeRuleCard from '@/components/AttributeRuleCard';
import useAttributeRules from '@/hooks/useAttributeRules';

export default function AttributeValuesPage() {
  const router = useRouter();
  const { ns, attrName } = router.query;
  const attributeRules = useAttributeRules(ns);
  const attributeObject = attributeRules.find(
    (o) => o.name === attrName && o.authorityNamespace === ns
  );

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      contentTitle={`Authority Namespace ${ns}`}
      // NOTE(PLAT-875): Deleted for demo
      // actions={[
      //   {
      //     key: 'edit-attribute',
      //     children: (
      //       <Button variant={Button.VARIANT.SECONDARY} size={Button.SIZE.MEDIUM}>
      //         Edit
      //       </Button>
      //     ),
      //   },
      //   {
      //     key: 'delete-attribute',
      //     children: (
      //       <Button variant={Button.VARIANT.NO_OUTLINE} size={Button.SIZE.MEDIUM}>
      //         Delete
      //       </Button>
      //     ),
      //   },
      // ]}
      actionAlignment={Page.ACTION_ALIGNMENTS.LEFT}
      title="Attribute"
      description="Information attached to data and entities that controls which entities can access which data."
    >
      <Page.Breadcrumb text="Attributes" href="/attributes" />
      <Page.Breadcrumb text={attrName} />
      {attributeObject && (
        <AttributeRuleCard
          name={attributeObject.name}
          authorityNamespace={attributeObject.authorityNamespace}
          values={attributeObject.order}
          accessType={attributeObject.rule}
          onNewValueAction={() => {}}
          onEditRuleAction={() => {}}
        />
      )}
    </Page>
  );
}
