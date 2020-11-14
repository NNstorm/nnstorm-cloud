"""
Module azure_api containing the AzureManager class,
which is responsible for Azure resource management and Azure client handling mechanism.
"""
import random
import string
import sys
import time
from pathlib import Path
from typing import List, Union

from msrestazure.azure_exceptions import CloudError
from nnstorm_cloud.azure.api import AzureApi, AzureError

from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import (
    BillingProfile,
    LinuxConfiguration,
    OSDisk,
    SshConfiguration,
    SshPublicKey,
    VirtualMachine,
    VirtualMachineEvictionPolicyTypes,
    VirtualMachinePriorityTypes,
)
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import (
    NetworkInterface,
    NetworkSecurityGroup,
    PublicIPAddress,
    PublicIPAddressDnsSettings,
    Subnet,
    VirtualNetwork,
)
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient


class AzureManager(AzureApi):
    """Azure Python API wrapper to help with common Azure tasks for VMs and deployments

    Raises:
        AzureError: When something goes wrong an AzureError with description is raised
    """

    def __init__(
        self,
        rsg: str = None,
        async_mode: bool = False,
        auth_path: Path = None,
        location: str = None,
        create_rsg: bool = True,
    ):
        """Initialize the AzureManager class, create rsg if it does not exist.

        Args:
            rsg (str, optional): name of the Azure resource group to use. Defaults to None.
            keyvault (str, optional): name of the keyvault. Defaults to None.
            async_mode (bool, optional): whether to use async mode. Defaults to False.
            auth_path (Path, optional): location of azure auth json file. Defaults to None.
            location (str, optional): location of the azure resource group
            create_rsg (bool, optional): whether to create the Azure rsg

        Raises:
            AzureError: If anything is misconfigured, an AzureError is raised.
        """
        super(AzureManager, self).__init__(auth_path)

        self._async_mode = async_mode

        self.config = {}
        self.rsg = rsg

        # create or update resource group if does not exist:
        if create_rsg:
            self.client(ResourceManagementClient).resource_groups.create_or_update(self.rsg, {"location": location})

            while True:
                time.sleep(0.5)
                rsg_state = (
                    self.client(ResourceManagementClient).resource_groups.get(self.rsg).properties.provisioning_state
                )
                if rsg_state == "Succeeded":
                    break

                self.logger.info("Waiting for RSG to be available.")

        self.logger.debug("Azure Manager API init completed.")

    def set_async(self, async_on: bool = True) -> None:
        """Set async mode

        Args:
            async_on (bool, optional): Whether to use async execution. Defaults to True.
        """
        self._async_mode = async_on

    def _async_wait(self, handle, force_wait=False) -> None:
        """If async mode is turned on, proceed, otherwise wait for handle's completion

        Args:
            handle {azure job handle}: Azure job handler (like process), for which to wait
            force_wait (bool, optional): If set, wait is enforced disregarding object setting. Defaults to False.
        """
        if not self._async_mode or force_wait:
            handle.wait()
        else:
            self.logger.debug("Request successful, async operation in progress")

    def virtual_machine(
        self,
        name: str,
        network_interface: NetworkInterface = None,
        image: dict = None,
        size: str = "Standard_B2s",
        user: str = None,
        password: str = None,
        spot_instance: bool = True,
        max_price_per_hour: float = 2.0,
        disk_size_gb: int = 32,
        ssh_pubkey: str = None,
    ) -> VirtualMachine:
        """Get existing / Create new a Virtual Machine in Azure

        Args:
            name (str): Name of the virtual machine
            network_interface (NetworkInterface, optional): network interface to use. Defaults to None.
            image (dict, optional): image description to use. Defaults to None.
            size (str, optional): size of the VM. Defaults to "Standard_B2s".
            user (str, optional): default username. Defaults to None.
            password (str, optional): user's password. Defaults to None.
            spot_instance (bool, optional): Whether to deploy a spot / pay as you go instance. Defaults to True.
            max_price_per_hour (float, optional): Max price/hour in euros. Defaults to 2.0.
            disk_size_gb (int, optional): Size of the OS disk. Defaults to 32.
            ssh_pubkey (str, optional): SSH public key for logging in as user. Defaults to None.

        Raises:
            AzureError: If VM creation is not successful.

        Returns:
            VirtualMachine: The created virtual machine's descriptor.
        """
        try:
            vm = self.client(ComputeManagementClient).virtual_machines.get(self.rsg, name)
        except CloudError:
            if not network_interface:
                raise AzureError("Cannot create VM without network interface, please supply it.")

            self.logger.info(f"Creating virtual machine: {name}")
        else:
            self.logger.info(f"Found virtual machine: {name}")
            return vm

        vm_params = {
            "location": self.config["location"],
            "os_profile": {"computer_name": name, "admin_username": user, "admin_password": password},
            "hardware_profile": {
                "vm_size": size,
                "os_disk": OSDisk(disk_size_gb=disk_size_gb, create_option="FromImage"),
            },
            "storage_profile": {"image_reference": image},
            "network_profile": {"network_interfaces": [network_interface]},
            "tags": {"persistent": "0", "development": "1"},
            "plan": self.config["nvidia_plan"],
        }

        if spot_instance:
            # use Azure spot instance
            vm_params["priority"] = VirtualMachinePriorityTypes.spot
            # For Azure Spot virtual machines, the only supported value is 'Deallocate'
            vm_params["eviction_policy"] = VirtualMachineEvictionPolicyTypes.deallocate
            # set max price
            vm_params["billing_profile"] = BillingProfile(max_price=max_price_per_hour)

        if ssh_pubkey:
            key_path = f"/home/{user}/.ssh/authorized_keys"
            pubkey = SshPublicKey(path=key_path, key_data=ssh_pubkey)
            vm_params["os_profile"]["linux_configuration"] = LinuxConfiguration(
                ssh=SshConfiguration(public_keys=[pubkey])
            )

        self.logger.info(f"Creating VM:  {name}")

        vm_job = self.client(ComputeManagementClient).virtual_machines.create_or_update(self.rsg, name, vm_params)
        self._async_wait(vm_job)

        vm = self.client(ComputeManagementClient).virtual_machines.get(self.rsg, name)

        self.logger.info(f"Created VM: {vm.name}")
        return vm

    def delete(self, resource: object) -> None:
        """Delete resource from Azure

        Args:
            resource (object): An existing Azure resource.

        Raises:
            AzureError: If resource object does not have delete functionality
        """
        self.logger.info("Delete {resource.__class__.__name__}: {resource.name}")

        if isinstance(resource, VirtualMachine):
            async_delete = self.client(ComputeManagementClient).virtual_machines.delete(self.rsg, resource.name)
            async_delete.wait()
        else:
            raise AzureError(f"Object's class is unknown to delete functionality.")

    def network_security_group(self, name: str) -> NetworkSecurityGroup:
        """Get existing / create new network security group

        Args:
            name (str): name of the NSG

        Returns:
            NetworkSecurityGroup: The created / existing NSG's Azure API object
        """
        # get resource if exists
        try:
            nsg = self.client(NetworkManagementClient).network_security_groups.get(self.rsg, name)
        except CloudError:
            self.logger.info(f"Creating or updating nsg: {name}")
        else:
            self.logger.debug(f"Found network security group: {name}")
            return nsg

        nsg_job = self.client(NetworkManagementClient).network_security_groups.create_or_update(
            self.rsg, name, {"location": self.get_location()}
        )
        self._async_wait(nsg_job)

        nsg = self.client(NetworkManagementClient).network_security_groups.get(self.rsg, name)

        return nsg

    def allow_nsg_development(self, nsg: NetworkSecurityGroup, from_ip: str = "*") -> None:
        """Allow development related ports in a given network security group

        Args:
            nsg (NetworkSecurityGroup): NSG in which to enable dev ports
            from_ip (str, optional): The source ip, by default can be any. Defaults to "*".
        """
        self.logger.info(f"Enabling ssh in network security group: {nsg.name}")
        params = {
            "protocol": "Tcp",
            "source_port_range": "*",
            "destination_port_ranges": ["22", "20022", "6006", "6666", "8888", "8889", "6007", "80", "8080"],
            "source_address_prefix": from_ip,
            "destination_address_prefix": "*",
            "priority": 200,
            "direction": "Inbound",
            "access": "Allow",
        }

        security_rule_job = self.client(NetworkManagementClient).security_rules.create_or_update(
            self.rsg, nsg.name, "dev_ports", params
        )
        self._async_wait(security_rule_job)

        self.logger.info(f"Enabled ssh in network security group: {nsg.name}")

    def allow_nsg_ping(self, nsg: NetworkSecurityGroup, from_ip: str = "*") -> None:
        """Allow ping in a given network security group

        Args:
            nsg (NetworkSecurityGroup): NSG in which to enable ping
            from_ip (str, optional): The source ip, by default can be any. Defaults to "*".
        """
        self.logger.info(f"Enabling ping in network security group: {nsg.name}")
        params = {
            "protocol": "ICMP",
            "source_port_range": "*",
            "destination_port_range": "*",
            "source_address_prefix": from_ip,
            "destination_address_prefix": "*",
            "priority": 100,
            "direction": "Inbound",
            "access": "Allow",
        }

        security_rule_job = self.client(NetworkManagementClient).security_rules.create_or_update(
            self.rsg, nsg.name, "ping_rule", params
        )
        self._async_wait(security_rule_job)

        self.logger.info(f"Enabled ping in network security group: {nsg.name}")

    def virtual_network(self, name: str, address_prefixes: List[str] = None) -> VirtualNetwork:
        """Get existing / create new virtual network with given address prefixes.

        Args:
            name (str): Name of the virtual network
            address_prefixes {List[str], optional}: Address prefixes in vnet. Defaults to None.

        Raises:
            AzureError: If creation is not successful

        Returns:
            VirtualNetwork: The created vnet's Azure API object
        """
        try:
            vnet = self.client(NetworkManagementClient).virtual_networks.get(self.rsg, name)
        except CloudError:
            self.logger.info(f"Creating or updating virtual network: {name}")
        else:
            self.logger.debug(f"Found virtual network: {name}")
            return vnet

        if not address_prefixes:
            raise AzureError("Cannot create vnet without specified address prefix.")

        vnet_config = {
            "location": self.get_location(),
            "address_space": {"address_prefixes": address_prefixes},
        }

        async_vnet_creation = self.client(NetworkManagementClient).virtual_networks.create_or_update(
            self.rsg, name, vnet_config
        )
        self._async_wait(async_vnet_creation)

        vnet = self.client(NetworkManagementClient).virtual_networks.get(self.rsg, name)

        self.logger.info(f"Created vnet: {name}")
        return vnet

    def subnet(
        self,
        name: str,
        vnet: VirtualNetwork,
        address_prefix: str = None,
        nsg: NetworkSecurityGroup = None,
    ) -> Subnet:
        """Create/Get subnetwork in a given virtual network

        Args:
            name (str): name of the subnet
            vnet (VirtualNetwork): the virtual network object
            address_prefix (str, optional): address prefix inside the vnet. Defaults to None.
            nsg (NetworkSecurityGroup, optional): network security group. Defaults to None.

        Raises:
            AzureError: If the subnet could not be created

        Returns:
            Subnet: The created / already existing subnetwork.
        """
        try:
            subnet = self.client(NetworkManagementClient).subnets.get(self.rsg, vnet.name, name)
        except CloudError:
            self.logger.info(f"Creating or updating subnet: {name}")
        else:
            self.logger.debug(f"Found subnet: {name}")
            return subnet

        if not address_prefix:
            raise AzureError("Cannot create vnet without specified address prefix.")

        subnet_config = {
            "address_prefix": address_prefix,
        }

        if nsg:
            subnet_config["network_security_group"] = nsg

        async_subnet_creation = self.client(NetworkManagementClient).subnets.create_or_update(
            self.rsg, vnet.name, name, subnet_config
        )

        self._async_wait(async_subnet_creation)

        subnet = self.client(NetworkManagementClient).subnets.get(self.rsg, vnet.name, name)

        self.logger.info(f"Created subnet: {name}")
        return subnet

    def public_ip(self, name: str, dns_name: str = None) -> PublicIPAddress:
        """Get existing / Create new Public IP address on Azure

        Args:
            name (str): Name of the public IP address
            dns_name (str, optional): DNS name, if empty same as IP name. Defaults to None.

        Returns:
            PublicIPAddress: The created/existing public IP in Azure.
        """
        if not dns_name:
            dns_name = name

        # get resource if exists
        try:
            public_ip = self.client(NetworkManagementClient).public_ip_addresses.get(self.rsg, name)
        except CloudError:
            self.logger.info(f"Creating or updating Public IP: {name}")
        else:
            self.logger.debug(f"Found public IP: {name}")
            return public_ip

        params = {
            "location": self.get_location(),
            "public_ip_allocation_method": "Static",
            "sku": {"name": "Standard"},
        }

        if dns_name:
            params["dns_settings"] = PublicIPAddressDnsSettings(domain_name_label=dns_name)

        self.logger.info("Creating public IP")
        ip_job = self.client(NetworkManagementClient).public_ip_addresses.create_or_update(self.rsg, name, params)
        self._async_wait(ip_job)

        public_ip = self.client(NetworkManagementClient).public_ip_addresses.get(self.rsg, name)

        self.logger.info(f"Created public IP: {name}")
        return public_ip

    def network_interface(
        self,
        name: str,
        subnet: Subnet,
        nsg: NetworkSecurityGroup = None,
        public_ip: PublicIPAddress = None,
    ) -> NetworkInterface:
        """Create/Get Network Interface
        If the network interface already exists, it simply gets returned.

        Args:
            name (str): Name of the network interface
            subnet (Subnet): Subnet object, in which to create NIC
            nsg (NetworkSecurityGroup, optional): Network security group. Defaults to None.
            public_ip (PublicIPAddress, optional): Public IP address of the NIC. Defaults to None.

        Returns:
            NetworkInterface: The created (or existing) network interface.
        """
        netclient = self.client(NetworkManagementClient)

        # get resource if exists
        try:
            nic = netclient.network_interfaces.get(self.rsg, name)
        except CloudError:
            self.logger.info(f"Creating or updating NIC: {name}")
        else:
            return nic

        if_config = {
            "location": self.config["location"],
            "ip_configurations": [{"name": name, "subnet": subnet, "primary": True}],
        }

        if nsg:
            if_config["network_security_group"] = nsg

        if public_ip:
            if_config["ip_configurations"][0]["public_ip_address"] = public_ip

        async_nic_creation = netclient.network_interfaces.create_or_update(self.rsg, name, if_config)
        self._async_wait(async_nic_creation)

        nic = netclient.network_interfaces.get(self.rsg, name)

        self.logger.info(f"Created network interface: {name}")
        return nic

    def list_vms(self) -> List[VirtualMachine]:
        """List available VMs in the AzureManager resource group

        Returns:
            List[VirtualMachine]: List of VM objects
        """
        vms = self.client(ComputeManagementClient).virtual_machines.list(self.rsg)
        for vm in vms:
            print("\tVM: {}".format(vm.name))
        return vms

    def delete_rsg(self, rsg=None) -> None:
        """Delete the AzureManager resource group"""
        if not rsg:
            rsg = self.rsg
        self.logger.info(f"Removing rsg: {rsg}...")
        delete_async_operation = self.client(ResourceManagementClient).resource_groups.delete(rsg)

        if self._async_mode:
            self.logger.warning(f"Deletion requested from Azure, this might take a while to finish.")
        else:
            self.logger.info("Deleting Azure resource group, it might take >5min...")
            try:
                self._async_wait(delete_async_operation)
            except KeyboardInterrupt:
                self.logger.warning(f"Deletion requested from Azure, this might take a while to finish.")
                sys.exit(0)

    @staticmethod
    def generate_password(length=20, punctuation=True) -> str:
        """Generate random password to be used for passwords

        Args:
            length (int, optional): Length of the password. Defaults to 20.

        Returns:
            str: password
        """
        chars = string.ascii_letters + string.digits + ("+$_.;:,<>-[]{}" if punctuation else "")
        return "".join(random.SystemRandom().choice(chars) for i in range(length))

    def check_storage_available(self, name: str) -> bool:
        """Checks if storage account name is available

        Args:
            name (str): name of the account

        Returns:
            bool: If the storage account name is available
        """
        available = self.client(StorageManagementClient).storage_accounts.check_name_availability(name)
        return available.name_available

    def get_subnet_id(self, rsg: str, vnet_name: str, subnet_name: str) -> str:
        """Create Azure subnet ID from parameters

        Args:
            rsg (str): VNET resource group
            vnet_name (str): name of the virtual network
            subnet_name (str): name of the subnet

        Returns:
            str: subnet ID
        """
        return f"{self.get_vnet_id(rsg, vnet_name)}/subnets/{subnet_name}"

    def get_vnet_id(self, rsg: str, vnet_name: str) -> str:
        """Get virtual network ID

        Args:
            rsg (str): virtual network resource group
            vnet_name (str): [description]

        Returns:
            str: The virtual network ID
        """
        return f"/subscriptions/{self.subscription_id}/resourceGroups/{rsg}/providers/Microsoft.Network/virtualNetworks/{vnet_name}"

    def get_location(self) -> str:
        """Get the location of the resource group

        Returns:
            str: Azure location
        """
        return self.client(ResourceManagementClient).resource_groups.get(self.rsg).location
