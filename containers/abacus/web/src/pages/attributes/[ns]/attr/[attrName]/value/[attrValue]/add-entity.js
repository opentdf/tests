import { useRouter } from 'next/router';
import AttributeEntityAssigner from '@/components/AttributeEntityAssigner';
import { Button } from '@/components/Virtruoso';
import Page from '@/components/Page';
import generateTestIds from '@/helpers/generateTestIds';
import useRoutePath from '@/hooks/useRoutePath';

import styles from './add-entity.module.css';

export const testIds = generateTestIds('add-entity-page', [
  'editAction',
  'deleteAction',
  'cancelAction',
]);

export default function AttributesPage() {
  const router = useRouter();
  const routePath = useRoutePath();

  const { attrName, attrValue, ns } = router.query;

  const actions = [
    // NOTE(PLAT-875): Deleted for demo
    // {
    //   key: 'edit',
    //   children: (
    //     <Button
    //       variant={Button.VARIANT.SECONDARY}
    //       size={Button.SIZE.MEDIUM}
    //       onClick={() => routePath.pushAttributeValue('edit')}
    //       data-testid={testIds.editAction}
    //     >
    //       Edit
    //     </Button>
    //   ),
    // },
    // {
    //   key: 'delete',
    //   children: (
    //     <Button
    //       variant={Button.VARIANT.NO_OUTLINE}
    //       size={Button.SIZE.MEDIUM}
    //       data-testid={testIds.deleteAction}
    //     >
    //       Delete
    //     </Button>
    //   ),
    // },
  ];

  return (
    <Page
      actions={actions}
      actionAlignment={Page.ACTION_ALIGNMENTS.LEFT}
      title="Attribute"
      description="Information attached to data and entities that controls which entities can access which data."
      contentTitle={`Assign entity to "${attrName}:${attrValue}"`}
      contentType={Page.CONTENT_TYPES.EDIT}
    >
      <Page.Breadcrumb key="attributes" href={routePath.paths.attribute.ns} text="Attributes" />
      <Page.Breadcrumb
        key="attribute-name"
        // NOTE(PLAT-875): Deleted for demo
        // href={routePath.paths.attribute.attr}
        text={attrName}
      />
      <Page.Breadcrumb key="attribute-value" text={attrValue} />
      {ns && attrName && attrValue ? (
        <AttributeEntityAssigner
          namespace={ns}
          attributeName={attrName}
          attributeValue={attrValue}
          onSuccess={(entityId) => routePath.pushAttributeValue(undefined, { entityId })}
        />
      ) : null}
      <div className={styles.action}>
        <Button
          variant={Button.VARIANT.SECONDARY}
          size={Button.SIZE.MEDIUM}
          onClick={() => router.back()}
          data-testid={testIds.cancelAction}
        >
          Cancel
        </Button>
      </div>
    </Page>
  );
}
