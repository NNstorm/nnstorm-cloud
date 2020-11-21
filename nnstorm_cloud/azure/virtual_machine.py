"""
Azure virtual machine module, which has the AzureVM class.
"""
import logging
import subprocess
import time
from pathlib import Path
from typing import Union

from nnstorm_cloud.azure.api import AzureError
from nnstorm_cloud.azure.manager import AzureManager

from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import VirtualMachine


class AzureVM:
    """Azure Virtual Machine API wrapper with OO Design and type hinting"""

    def __init__(self, api: AzureManager, azure_vm: Union[VirtualMachine, str], spot_instance=True):
        """Create an Azure VM object from a name or an Actual Azure VM instance
        If only a name is given, the VM will not get deployed until running the deploy function.

        Args:
            api (AzureManager): The API object to manage Azure
            azure_vm (Union[VirtualMachine, str]): Name of the VM or VM instance
            spot_instance (bool, optional): Determines if a spot instance should be created. Defaults to True.
        """
        self.api = api
        self._spot_instance = spot_instance

        if isinstance(azure_vm, str):
            self.name = azure_vm
            # try to get instance if exists:
            try:
                vm = api.virtual_machine(self.name)
            except AzureError:
                self.vm = None
            else:
                self.vm = vm
        elif isinstance(azure_vm, VirtualMachine):
            self.name = azure_vm.name
            self.vm = azure_vm

        self._fqdn = None

        self.logger = logging.getLogger(f"AzureVM-{self.name}")
        self.logger.info("VM api available.")
        self.default_ip_name = f"{self.name}-{self.api.rsg}"

    def deploy(
        self,
        nsg_name: str = None,
        vnet_name: str = None,
        vnet_addresses: str = None,
        subnet_name: str = None,
        subnet_address: str = None,
        public_ip_name: str = None,
        nic_name: str = None,
        user: str = None,
        password: str = None,
        image: str = None,
        size: str = None,
        ssh_pubkey: str = None,
    ) -> None:
        """Deploys the virtual machine in Azure if it's not yet deployed.
        All of the needed services (network, etc.) will automatically get deployed.

        Args:
            nsg_name (str, optional): network security group name. Defaults to None.
            vnet_name (str, optional): virtual network name. Defaults to None.
            vnet_addresses (str, optional): virtual network address range. Defaults to None.
            subnet_name (str, optional): subnetwork name. Defaults to None.
            subnet_address (str, optional): subnetwork address ranges. Defaults to None.
            public_ip_name (str, optional): public ip name. Defaults to None.
            nic_name (str, optional): network interface name. Defaults to None.
            user (str, optional): user name. Defaults to None.
            password (str, optional):  password. Defaults to None.
            image (str, optional): image name. Defaults to None.
            size (str, optional): size of the virtual machine. Defaults to None.
            ssh_pubkey (str, optional): pubkey string for ssh login. Defaults to None.
        """
        if self.vm:
            self.logger.info("VM is already deployed, deployment step is skipped.")
            return

        if not nsg_name:
            nsg_name = self.api.config["nsg"]
        if not vnet_name:
            vnet_name = self.api.config["vnet"]
        if not vnet_addresses:
            vnet_addresses = self.api.config["vnet_addresses"]
        if not subnet_name:
            subnet_name = self.api.config["subnet"]
        if not subnet_address:
            subnet_address = self.api.config["subnet_address"]
        if not public_ip_name:
            public_ip_name = self.default_ip_name
        if not nic_name:
            nic_name = f"{self.name}-nic"
        if not user:
            user = self.api.keyvault.get_secret(self.api.config["secrets"]["username"])
        if not password:
            password = self.api.keyvault.get_secret(self.api.config["secrets"]["password"])
        if not image:
            image = self.api.config["ubuntu_image"]
        if not size:
            size = "small"

        # create network
        nsg = self.api.network_security_group(nsg_name)
        self.api.allow_nsg_development(nsg)
        self.api.allow_nsg_ping(nsg)

        vnet = self.api.virtual_network(vnet_name, address_prefixes=vnet_addresses)

        subnet = self.api.subnet(
            subnet_name,
            vnet=vnet,
            nsg=nsg,
            address_prefix=subnet_address,
        )

        public_ip = self.api.public_ip(public_ip_name)

        nic = self.api.network_interface(nic_name, subnet=subnet, nsg=nsg, public_ip=public_ip)

        self.vm = self.api.virtual_machine(
            self.name,
            nic,
            image,
            self.api.config["vm_sizes"][size],
            user,
            password,
            self._spot_instance,
            max_price_per_hour=1.0,
            disk_size_gb=64,
            ssh_pubkey=ssh_pubkey,
        )

    def get_fqdn(self, public_ip_name: str = None) -> str:
        """Get Fully Qualified Domain Name (DNS name) of a public IP

        Args:
            public_ip_name (str, optional): name of the public IP. Defaults to None.

        Returns:
            str: the FQDN of the public IP
        """
        if not self._fqdn:
            if not public_ip_name:
                public_ip_name = self.default_ip_name
            self._fqdn = self.api.public_ip(public_ip_name).dns_settings.fqdn
        return self._fqdn

    def execute_command(self, command: str, user: str = "root") -> str:
        """Execute command on the VM

        Args:
            command (str): string which will run on VM, do not use double quote!!!
            user (str, optional): username. Defaults to "root".

        Returns:
            str: the string response with stdout and stderr
        """
        if user:
            command = f'runuser -l  {user} -c "{command}"'
        run_command_parameters = {
            "command_id": "RunShellScript",
            "script": [command],
            "parameters": [],
        }

        poller = self.api.client(ComputeManagementClient).virtual_machines.run_command(
            self.api.rsg, self.vm.name, run_command_parameters
        )

        poller.wait()
        result = poller.result()  # Blocking till executed
        self.api.logger.debug(f"Exec result:\n {result.value[0].message}")

        return result.value[0].message

    def execute_shell_script(self, local_path, user: str = "root") -> None:
        """Execute a local shell script on  the VM

        Args:
            local_path ([type]): Path to the script
            user (str, optional):  the user which runs the script. Defaults to "root".
        """
        raise NotImplementedError  # TODO

    def restart(self) -> None:
        """Restart the VM"""
        async_vm_restart = self.api.client(ComputeManagementClient).virtual_machines.restart(self.api.rsg, self.vm.name)
        self.api._async_wait(async_vm_restart)

    def power_off(self) -> None:
        """Power off the VM"""
        async_vm_stop = self.api.client(ComputeManagementClient).virtual_machines.power_off(self.api.rsg, self.vm.name)
        self.api._async_wait(async_vm_stop)

    def start(self) -> None:
        """Start the stopped VM"""
        async_vm_start = self.api.client(ComputeManagementClient).virtual_machines.start(self.api.rsg, self.vm.name)
        self.api._async_wait(async_vm_start)

    def wait_for_service(self, ssh_port: int = 22) -> None:
        """Wait for services to come up: ping should work and ssh listening on given port

        Args:
            ssh_port (int): The port on which SSH listens. Defaults to 22.
        """
        ping, ssh = False, False
        while (not ping) or (not ssh):
            if not ping:
                process = subprocess.Popen(
                    ["ping", "-c", "1", self.get_fqdn()], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                process.communicate()
                if process.poll() == 0:
                    ping = True

            if not ssh:
                process = subprocess.Popen(
                    ["ssh", "-p", str(ssh_port), "-o", "StrictHostKeyChecking=no", "-t", self.get_fqdn(), "echo hi"],
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                process.communicate()
                if process.poll() == 0:
                    ssh = True
            if not ping or not ssh:
                time.sleep(1)
                self.api.logger.debug(
                    f"Waiting for service: Ping [{'OK' if ping else 'FAILED'}],"
                    f" SSH on port {ssh_port} [{'OK' if ssh else 'FAILED'}]"
                )

    def add_ssh_config_entry(self, entry_name: str = "cloud-gpu") -> None:
        """Add SSH config entry to $HOME/.ssh/config for easy access of the vm

        Args:
            entry_name (str, optional): Name of the entry in the config. Defaults to "cloud-gpu".
        """
        self.remove_ssh_config_entry(entry_name)

        entry = (
            f"\nHost {entry_name}\n"
            f"     StrictHostKeyChecking no\n"
            f"     HostName {self.get_fqdn()}\n"
            f"     ForwardX11 yes\n"
            f"     Port 20022\n"
        )
        with open(Path.home() / ".ssh/config", "a") as f:
            f.write(entry)

    def remove_ssh_config_entry(self, entry_name: str = "cloud-gpu") -> None:
        """Remove the ssh config entry for the vm in $HOME/.ssh/config

        Args:
            entry_name (str, optional): The ssh config entry to remove. Defaults to "cloud-gpu".
        """
        config_path = Path.home() / ".ssh/config"
        if not config_path.is_file():
            return
        with config_path.open("r") as f:
            config = f.readlines()
        found = False
        done = False
        clean_config = []
        for line in config:
            if f"Host {entry_name}" in line:
                found = True
            elif found:
                if "Host " in line:
                    done = True
            if not (found and not done):
                clean_config.append(line)
        with open(Path.home() / ".ssh/config", "w") as f:
            f.writelines(clean_config)

    def delete_from_known_hosts(self) -> None:
        """Delete the VM's entry from the known hosts file to eliminate warnings and spamming."""
        with open(Path.home() / ".ssh/known_hosts", "r") as f:
            hosts = f.readlines()
            hosts = [h for h in hosts if self.get_fqdn() not in h]
        with open(Path.home() / ".ssh/known_hosts", "w") as f:
            f.writelines(hosts)

    def check_vm_exists(self) -> None:
        """Asserts that the VM exists and raises an RuntimeError if not

        Raises:
            RuntimeError: If the VM does not exist a RuntimeError is raised by the function
        """
        if not self.vm:
            raise RuntimeError(f"Requested vm {self.name} does not exist in rsg {self.api.rsg}")
