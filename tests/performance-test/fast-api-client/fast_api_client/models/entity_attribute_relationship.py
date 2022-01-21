from typing import Any, Dict, List, Type, TypeVar

import attr

T = TypeVar("T", bound="EntityAttributeRelationship")


@attr.s(auto_attribs=True)
class EntityAttributeRelationship:
    """ """

    attribute: str
    entity_id: str
    state: str
    additional_properties: Dict[str, Any] = attr.ib(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        attribute = self.attribute
        entity_id = self.entity_id
        state = self.state

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "attribute": attribute,
                "entityId": entity_id,
                "state": state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        d = src_dict.copy()
        attribute = d.pop("attribute")

        entity_id = d.pop("entityId")

        state = d.pop("state")

        entity_attribute_relationship = cls(
            attribute=attribute,
            entity_id=entity_id,
            state=state,
        )

        entity_attribute_relationship.additional_properties = d
        return entity_attribute_relationship

    @property
    def additional_keys(self) -> List[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
