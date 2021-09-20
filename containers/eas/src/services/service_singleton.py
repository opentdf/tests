from .abstract_attribute_service import AbstractAttributeService
from .abstract_authority_ns_service import AbstractAuthorityNamespaceService
from .abstract_entity_attr_rel import AbstractEntityAttributeRelationshipService
from .abstract_entity_service import AbstractEntityService
from .attribute_name_service_setup import setup_attribute_name_service
from .attribute_service_setup import setup_attribute_service
from .authority_ns_service_setup import setup_authority_ns_service
from .entity_attr_rel_setup import setup_entity_attr_rel_service
from .entity_object_service import EntityObjectService
from .entity_service_setup import setup_entity_service
from ..eas_config import EASConfig
from ..errors import Error


class ServiceSingleton(object):
    """Hold the current services so web methods and tests can access/update them."""

    __instance = None

    @staticmethod
    def get_instance():
        if ServiceSingleton.__instance is None:
            # Create the singleton instance
            return ServiceSingleton()
        return ServiceSingleton.__instance

    def __init__(self) -> None:
        if ServiceSingleton.__instance is not None:
            raise Error("ServiceSingleton is a singleton")
        # Determine the service config needed
        eas_config = EASConfig.get_instance()

        # Create the service instances using the setup/factory functions
        self.ear_service: AbstractEntityAttributeRelationshipService = (
            setup_entity_attr_rel_service()
        )
        self.authority_ns_service: AbstractAuthorityNamespaceService = (
            setup_authority_ns_service()
        )
        self.attribute_service: AbstractAttributeService = setup_attribute_service()
        self.entity_service: AbstractEntityService = setup_entity_service(
            self.ear_service
        )

        self.entity_object_service = EntityObjectService(
            self.entity_service, self.attribute_service
        )
        self.attribute_name_service = setup_attribute_name_service(
            self.authority_ns_service,
            self.attribute_service,
            default_namespace=eas_config.get_item("DEFAULT_NAMESPACE"),
        )

        ServiceSingleton.__instance = self
