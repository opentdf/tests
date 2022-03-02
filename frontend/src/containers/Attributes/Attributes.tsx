import { List, Spin } from "antd";
import { useAttributesFilters, useAuthorities } from "../../hooks";
import { AttributesFiltersStore } from "../../store";
import { AttributeListItem } from "../AttributeListItem";
import CreateAttribute from "./CreateAttribute";
import { AttributesHeader } from "./components";

import "./Attributes.css";

const Attributes = () => {
  useAuthorities();
  const authority = AttributesFiltersStore.useState(s => s.authority);
  const attrsQueryParams = AttributesFiltersStore.useState(s => s.query);
  const { attrs, loading, xTotalCount } = useAttributesFilters(authority, attrsQueryParams);

  return (
    <>
      <AttributesHeader total={xTotalCount} />
      { loading
        ? (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            width: '100%',
            justifyContent: 'center',
            height: '300px',
          }}>
            <h1 style={{ marginBottom: '0', marginRight: '15px', fontSize: '30px' }}>loading... </h1>
            <Spin size="large" />
          </div>
        )
        : (
          <>
            <List grid={{ gutter: 3, xs: 2, column: 2 }}>
              {attrs.map((attr) => (
                <AttributeListItem
                  activeAuthority={authority}
                  attr={attr}
                  key={attr.name}
                />
              ))}
            </List>
            <CreateAttribute
              authority={authority}
              onAddAttr={() => {}}
              onAddNamespace={() => {}}
            />
          </>
        )
      }
    </>
  );
};

export default Attributes;
