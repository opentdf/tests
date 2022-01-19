import { FC, memo, useCallback } from "react";
import { Affix, Card, Collapse, Typography } from "antd";
import { toast } from "react-toastify";

import { useLazyFetch } from "../../hooks/useFetch";
import { Attribute } from "../../types/attributes";
import { attributesClient } from "../../service";
import { Method } from "../../types/enums";
import { CreateAttributeForm, CreateAuthorityForm } from "./components";

const { Panel } = Collapse;

type Props = {
  authorityNamespace: string;
  onAddAttr: (attr: Attribute) => void;
  onAddNamespace: (namespace: string) => void;
};

type CreateAttributeValues = Omit<Attribute, "authorityNamespace">;
type CreateAuthorityValues = {
  request_authority_namespace: string;
};

const CreateAttribute: FC<Props> = (props) => {
  const { authorityNamespace, onAddAttr, onAddNamespace } = props;

  const [createAuthority] = useLazyFetch(attributesClient);
  const [createAttributes] = useLazyFetch(attributesClient);

  const handleCreateAuthority = useCallback(
    (values: CreateAuthorityValues) => {
      createAuthority<string[]>({
        method: Method.POST,
        path: `/attributes/v1/authorityNamespace`,
        params: {
          params: {
            request_authority_namespace: values.request_authority_namespace,
          },
        },
      })
        .then((response) => {
          const [lastItem] = response.data.slice(-1);
          toast.success("Authority was created");
          onAddNamespace(lastItem);
        })
        .catch(() => {
          toast.error("Authority was not created");
        });
    },
    [createAuthority, onAddNamespace],
  );

  const handleCreateAttribute = (values: CreateAttributeValues) => {
    createAttributes<Attribute>({
      method: Method.POST,
      path: `/attributes/v1/attr`,
      data: { ...values, authorityNamespace },
    })
      .then((response) => {
        onAddAttr(response.data);
        toast.success(`Attribute created for ${authorityNamespace}`);
      })
      .catch(() => {
        toast.error(`Attribute was no created for ${authorityNamespace}`);
      });
  };

  return (
    <Affix offsetBottom={1}>
      <div>
        <Collapse>
          <Panel
            header={<Typography.Title level={2}>New</Typography.Title>}
            key="1"
          >
            <Card>
              <Card.Grid>
                <CreateAuthorityForm onFinish={handleCreateAuthority} />
              </Card.Grid>

              <Card.Grid>
                <CreateAttributeForm
                  onFinish={handleCreateAttribute}
                  authorityNamespace={authorityNamespace}
                />
              </Card.Grid>
            </Card>
          </Panel>
        </Collapse>
      </div>
    </Affix>
  );
};

export default memo(CreateAttribute);
