"""
Module azure_api containing the AzureApi class,
which is responsible for Azure resource management and Azure client handling mechanism.
"""
import json
import logging
from pathlib import Path
from typing import Type

from msrest.service_client import SDKClient
from nnstorm_cloud.azure.cred_wrapper import CredentialWrapper

from azure.common.credentials import ServicePrincipalCredentials
from azure.graphrbac import GraphRbacManagementClient
from azure.identity import ClientSecretCredential


class AzureError(RuntimeError):
    """Internal Azure error to propagate AzureManager related errors"""


class AzureApi:
    """Base class for Azure Xmind operations with logger and identity handling"""

    def __init__(self, azure_auth_path: Path):
        """Initialize the class including identity path, logger, logging configuration.

        Args:
            azure_auth_path (Path, optional): Azure identity file path, please refer to project readme.
                                              Defaults to None.

        Raises:
            AzureError: If the authentication was not successful.
        """
        AzureApi._suppress_azure_internal_logs()
        self.logger = logging.getLogger(AzureApi.__name__)

        if not azure_auth_path.is_file():
            raise AzureError()
        self.azure_auth_path = azure_auth_path

        self.client_secret_credentials = ClientSecretCredential(
            client_secret=self._get_client_secret(), client_id=self._get_client_id(), tenant_id=self._get_tenant_id()
        )
        self.service_principal_credentials = ServicePrincipalCredentials(
            client_id=self._get_client_id(), secret=self._get_client_secret(), tenant=self._get_tenant_id()
        )
        self.credentials = self._get_client_secret_credential()
        self.subscription_id = self._get_subscription_id()

        self._clients = {}

    def _load_azure_credential(self) -> dict:
        """Loads the azure identity file from the user's home folder (path is class variable).

        Returns:
            dict: the credential dict
        """
        with open(self.azure_auth_path, "r") as file:
            azure_json = json.load(file)
        return azure_json

    def _get_tenant_id(self) -> str:
        """Get the tenant ID for the service principal

        Returns:
            str: tenant ID
        """
        azure_auth = self._load_azure_credential()
        if "tenantId" in azure_auth:
            return azure_auth["tenantId"]
        else:
            return azure_auth["tenant"]

    def _get_client_id(self) -> str:
        """Get the client ID

        Returns:
            str: Client ID
        """
        azure_auth = self._load_azure_credential()
        if "clientId" in azure_auth:
            return azure_auth["clientId"]
        else:
            return azure_auth["appId"]

    def _get_client_secret(self) -> str:
        """Get the service principal's secret

        Returns:
            str: Client secret
        """
        azure_auth = self._load_azure_credential()
        if "clientSecret" in azure_auth:
            return azure_auth["clientSecret"]
        else:
            return azure_auth["password"]

    def _get_client_secret_credential(self, resource_id: str = None) -> ClientSecretCredential:
        """Get client secret credentials, which are mostly used with management clients.

        Returns:
            ClientSecretCredential: CS credentials to be used with clients
        """

        if resource_id:
            return CredentialWrapper(self.client_secret_credentials, resource_id=resource_id)
        else:
            return CredentialWrapper(self.client_secret_credentials)

    def _get_subscription_id(self) -> str:
        """Get the subscription ID string from auth file.

        Returns:
            str: Subscription ID on Azure
        """
        return self._load_azure_credential()["subscriptionId"]

    def get_object_id(self) -> str:
        """Get the RBAC object ID

        Returns:
            str: Object ID
        """
        graphrbac_credentials = ServicePrincipalCredentials(
            client_id=self._get_client_id(),
            secret=self._get_client_secret(),
            tenant=self._get_tenant_id(),
            resource="https://graph.windows.net",
        )
        graphrbac_client = GraphRbacManagementClient(
            graphrbac_credentials, self._get_tenant_id(), "https://graph.windows.net"
        )
        result = list(
            graphrbac_client.service_principals.list(
                filter="servicePrincipalNames/any(c:c eq '{}')".format(self._get_client_id())
            )
        )
        assert len(result[0].object_id) > 0
        return result[0].object_id

    @staticmethod
    def _suppress_azure_internal_logs() -> None:
        """Suppress Azure Python libraries internal verbose logs"""
        logging.getLogger("azure").setLevel(logging.WARNING)
        logging.getLogger("azure.core").setLevel(logging.WARNING)
        logging.getLogger("adal-python").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("msrest").setLevel(logging.WARNING)
        logging.getLogger("msal").setLevel(logging.WARNING)
        logging.getLogger("azure.storage").setLevel(logging.WARNING)
        logging.getLogger("azure.identity").setLevel(logging.WARNING)

    def client(self, client_class: Type[SDKClient]) -> SDKClient:
        """Get an Azure Management client by it's class using caching.
        All of these classes are inherited from SDKClient.
        If a class is requested multiple times, the same (cached) instance will be returned.

        Args:
            client_class (Type[SDKClient]): The client you want to use, for example ComputeManagementClient

        Returns:
            SDKClient: An object of the requested class is returned, and cached.
        """
        if client_class.__name__ not in self._clients:
            self.logger.debug(f"Creating client: {client_class.__name__}")
            self._clients[client_class.__name__] = client_class(self.credentials, self.subscription_id)

        return self._clients[client_class.__name__]
