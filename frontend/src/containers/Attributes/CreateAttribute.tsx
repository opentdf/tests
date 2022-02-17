import { FC, memo, useCallback } from "react";
import { Affix, Card, Collapse, Typography } from "antd";
import { toast } from "react-toastify";

import { useLazyFetch } from "../../hooks";
import {AttributeDefinition, AuthorityDefinition} from "../../types/attributes";
import { entityClient } from "../../service";
import { Method } from "../../types/enums";
import { CreateAttributeForm, CreateAuthorityForm } from "./components";

// @ts-ignore
const serverData = window.SERVER_DATA;
const { Panel } = Collapse;

type Props = {
  authority: AuthorityDefinition;
  onAddAttr: (attr: AttributeDefinition) => void;
  onAddNamespace: (namespace: string) => void;
};


const CreateAttribute: FC<Props> = (props) => {
  const { authority, onAddAttr, onAddNamespace } = props;

  const [createAuthority] = useLazyFetch(entityClient);
  const [createAttributes] = useLazyFetch(entityClient);

  const handleCreateAuthority = useCallback(
    (value: AuthorityDefinition) => {
      createAuthority<string[]>({
        method: Method.POST,
        path: serverData.attributes + `/authorities`,
        data: value,
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

  const handleCreateAttribute = (values: AttributeDefinition) => {
    createAttributes<AttributeDefinition>({
      method: Method.POST,
      path: serverData.attributes + `/definitions/attributes`,
      data: { ...values, authority },
    })
      .then((response) => {
        onAddAttr(response.data);
        toast.success(`Attribute created for ${authority}`);
      })
      .catch(() => {
        toast.error(`Attribute was no created for ${authority}`);
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
                  authority={authority}
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
