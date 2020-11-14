"""Helm Python wrapper"""

import logging
from pathlib import Path
from typing import List, Union

from nnstorm_cloud.core.utils import run_shell_command

repos = []


class HelmAPI:
    """Python HELM API"""

    def __init__(self, namespace: str):
        """Create the Helm API object with a given namespace

        Args:
            namespace (str): Kubernetes namespace
        """
        self.namespace = namespace
        self.repos = []
        self.namespace_args = ["--namespace", self.namespace]

    def install(
        self,
        name: str,
        chart: Union[str, Path],
        config_map: dict,
        reinstall: bool = True,
        atomic: bool = True,
        timeout: str = "900s",
        extra_args: List[str] = [],
    ) -> None:
        """Install a Helm chart

        Args:
            name (str): name of the chart
            chart (Union[str, Path]): Path to the chart
            config_map (dict): dictionary of key-value pairs for the chart values
            reinstall (bool, optional): whether to uninstall the chart first. Defaults to True.
            atomic (bool, optional): atomic - so wait for the results. Defaults to True.
            timeout (str, optional): timeout for the installation. Defaults to "900s".
            extra_args (List, optional): extra HELM argument list. Defaults to [].
        """
        if reinstall:
            self.uninstall(name, tolerate_error=True)

        values = [f"{key}={value}" for key, value in config_map.items()]
        args = []
        for v in values:
            args.append("--set")
            args.append(v)

        if atomic:
            args.append("--atomic")
        args.append(f"--timeout={timeout}")
        args.append("--debug")

        helm_cmd = "install"
        if not reinstall and self.exists(name):
            helm_cmd = "upgrade"

        cmd = ["helm", helm_cmd, name, str(chart)] + self.namespace_args + args + extra_args

        run_shell_command(cmd)

    def uninstall(self, name: str, tolerate_error=False) -> None:
        """Uninstall HELM chart from cluster

        Args:
            name (str): name of the chart
            tolerate_error (bool, optional): if true, errors are tolerated. Defaults to False.

        Raises:
            RuntimeError: If error is not tolerated and something goes wrong
        """
        try:
            run_shell_command(["helm", "uninstall", name] + self.namespace_args)
        except RuntimeError as e:
            if not tolerate_error:
                raise e

    def exists(self, name: str) -> bool:
        """Check if HELM chart exists in namespace on cluster

        Args:
            name (str): name of the HELM chart

        Returns:
            bool: whether chart is installed
        """
        try:
            run_shell_command(["helm", "status", name] + self.namespace_args)
            return True
        except RuntimeError:
            return False

    def add_repo(self, branch: str, name: str) -> None:
        """Add and update repo from public repos

        Args:
            branch (str): branch name for the repo
            name (str): repo name
        """
        if name not in repos:
            run_shell_command(["helm", "repo", "add", branch, name])
            repos.append(name)

            retries = 10
            i = 0
            while True:
                try:
                    run_shell_command(["helm", "repo", "update"])
                except:
                    logging.error("Could not update HELM repo!")
                    i += 1
                else:
                    break

                if i == retries:
                    raise RuntimeError("Cannot update HELM repo!!")

    def deploy_ingress_controller(self, name: str, replicas: int = 2, controller_definition: Path = None) -> None:
        """Deploy a Kubernetes ingress controller

        Args:
            name (str): name of the deployment
            replicas (int, optional): replica count of containers. Defaults to 2.
            controller_definition (Path, optional): controller definition. Defaults to None.
        """
        self.add_repo("ingress-nginx", "https://kubernetes.github.io/ingress-nginx")
        self.add_repo("stable", "https://kubernetes-charts.storage.googleapis.com/")

        values = {
            "controller.replicaCount": replicas,
            "controller.nodeSelector.beta\.kubernetes\.io/os": "linux",
            "defaultBackend.nodeSelector.beta\.kubernetes\.io/os": "linux",
            "controller.admissionWebhooks.enabled": "false",
        }
        if controller_definition:
            args = ["-f", str(controller_definition)]
        else:
            args = []

        self.install(name, "ingress-nginx/ingress-nginx", values, reinstall=True, atomic=True, extra_args=args)

    def get_ingress_name(self, name: str) -> str:
        """Get the ingress controller name for a deployment

        Args:
            name (str): chart name

        Returns:
            str: ingress controller name
        """
        return f"{name}-ingress-nginx-controller"
