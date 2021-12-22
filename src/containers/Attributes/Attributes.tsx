import { useCallback, useEffect, useMemo, useState } from "react";
import { List } from "antd";

import { useAuthorities, useAttributesDefinitions } from "../../hooks";

import { AttributeListItem } from "../AttributeListItem";
import CreateAttribute from "./CreateAttribute";
import { AttributesHeader, AttributesListHeader } from "./components";

import "./Attributes.css";
import {AuthorityDefinition} from "../../types/attributes";

const Attributes = () => {
  const authorities = useAuthorities();
  const [authority] = authorities;

  const [stateAuthorities, setStateAuthorities] = useState(authorities);
  const [activeAuthority, setActiveAuthority] = useState(authority);
  const { attrs, getAttrs } = useAttributesDefinitions(activeAuthority);
  const [stateAttrs, setStateAttrs] = useState(attrs);

  useEffect(() => {
    setStateAttrs(attrs);
  }, [attrs]);

  useEffect(() => {
    setStateAuthorities(authorities);
  }, [authorities]);

  const handleAuthorityChange = useCallback((value: AuthorityDefinition) => {
    setActiveAuthority(value);
  }, []);

  const onAddAttr = useCallback((attr) => {
    setStateAttrs((prevState) => [...prevState, attr]);
  }, []);

  const onAddNamespace = useCallback(
    (namespace) => {
      setStateAuthorities((prevState) => [...prevState, namespace]);
      getAttrs(namespace);
    },
    [getAttrs],
  );

  const header = useMemo(
    () => (
      <AttributesListHeader
        activeAuthority={activeAuthority}
        authorities={stateAuthorities}
        authority={authority}
        onAuthorityChange={handleAuthorityChange}
      />
    ),
    [activeAuthority, stateAuthorities, authority, handleAuthorityChange],
  );

  return (
    <>
      <AttributesHeader />

      <List grid={{ gutter: 3, xs: 2, column: 2 }} header={header}>
        {stateAttrs.map((attr) => (
          <AttributeListItem
            activeAuthority={activeAuthority}
            attr={attr}
            key={attr.name}
          />
        ))}
      </List>

      <CreateAttribute
        authority={activeAuthority}
        onAddAttr={onAddAttr}
        onAddNamespace={onAddNamespace}
      />
    </>
  );
};

export default Attributes;
