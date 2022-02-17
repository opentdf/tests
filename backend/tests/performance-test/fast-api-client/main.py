import asyncio
import os
from typing import List

from fast_api_client import Client
from fast_api_client.api.default import (
    read_relationship_v1_entity_attribute_get,
    create_entity_attribute_relationship_v1_entity__entity_id__attribute_put,
)
from fast_api_client.models import EntityAttributeRelationship


async def main():
    client = Client(base_url=os.environ["EAS_ENDPOINT"])
    # put
    attributes = []
    i = 0
    while i < 10:
        attributes.append(f"https://eas.local/attr/{i}/value/{i}")
        i += 1
    await create_entity_attribute_relationship_v1_entity__entity_id__attribute_put.asyncio(
        client=client, entity_id="entity1", json_body=attributes
    )
    # get
    relationships: List[
        EntityAttributeRelationship
    ] = await read_relationship_v1_entity_attribute_get.asyncio(client=client)
    print(relationships)


if __name__ == "__main__":
    asyncio.run(main())
