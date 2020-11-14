""" Kubectl Kubernetes CLI Python wrapper """
import json
import logging
import time
from pathlib import Path
from typing import List, Tuple

from nnstorm_cloud.core.utils import run_shell_command


def get_latest_version_on_azure(location: str) -> str:
    """Get latest available AKS cluster version

    Args:
        location (str): name of the Azure location

    Returns:
        str: latest version
    """
    out, _ = run_shell_command(["az", "aks", "get-versions", "-l", location, "-o", "json"])
    versions = json.loads(out)["orchestrators"]
    stable = [i["orchestratorVersion"] for i in versions if not i["isPreview"]]
    stable.sort()
    return stable[-1]


class KubeControl:
    """Wrapper around the kubectl CLI tool"""

    def __init__(self, namespace: str, wait: bool = True):
        """Create the kubectl object with a namespace

        Args:
            namespace (str): namespace name
            wait (bool, optional): wait for requests to finish. Defaults to True.
        """
        self.namespace = namespace
        self.wait_args = [] if not wait else ["--wait"]

    def kube_cmd(self, args: List[str], namespaced: bool = True) -> Tuple[str, str]:
        """Run a kubectl command with given arguments in a given namespace

        Args:
            args (list): kubectl command arguments in order
            namespaced (bool, optional): whether to run it in cluster level or namespaced. Defaults to True.

        Returns:
            Tuple[str, str]: output, error of the run shell command
        """
        namespace_args = [] if not namespaced else ["--namespace", self.namespace]
        wait_args = [] if args[0] in ["create", "get", "rollout", "label", "scale", "logs"] else self.wait_args

        return run_shell_command(["kubectl"] + args + namespace_args + wait_args, poll=False)

    def delete_namespace(self, tolerate_error: bool = False) -> None:
        """Delete the object namespace

        Args:
            tolerate_error (bool, optional): whether to tolerate deletion errors. Defaults to False.

        Raises:
            RuntimeError: if errors are not tolerated.
        """
        logging.info(f"Deleting namespace: {self.namespace}")
        try:
            self.kube_cmd(["delete", "namespace", self.namespace], namespaced=False)
        except RuntimeError:
            logging.warning("Namespace did not exist, not deleted.")
            if not tolerate_error:
                raise RuntimeError("Could not delete namespace")

    def delete_resource(
        self, resource_type: str, resource_name: str, namespaced: bool = False, tolerate_error: bool = False
    ) -> None:
        """Delete a resource from the kubernetes cluster

        Args:
            resource_type (str): type of the resource (like secret deployment)
            resource_name (str): name of the resource to delete
            namespaced (bool, optional): if the deletion should happen only in namespace scope. Defaults to False.
            tolerate_error (bool, optional): whether to tolerate error during deletion. Defaults to False.

        Raises:
            RuntimeError: If error is not tolerated during deletion
        """
        try:
            cmd = ["delete", resource_type, resource_name]
            self.kube_cmd(cmd, namespaced=namespaced)
        except RuntimeError:
            logging.warning("Resource did not exist, not deleted.")
            if not tolerate_error:
                raise RuntimeError("Could not delete resource")

    def delete_path(self, path: Path, tolerate_error: bool = False):
        """Delete resources identified by a path to their yaml

        Args:
            path (Path): configration (directory or yaml) to remove
            tolerate_error (bool, optional): whether to tolerate error. Defaults to False.

        Raises:
            RuntimeError: if error is not tolerated
        """
        try:
            self.kube_cmd(["delete", "-f", str(path)], namespaced=False)
        except RuntimeError:
            logging.warning("Resource did not exist, not deleted.")
            if not tolerate_error:
                raise RuntimeError("Could not delete resource")

    def create_namespace(self) -> None:
        """Create namespace in the cluster

        Raises:
            RuntimeError: If namespace already exists or cannot be created
        """
        logging.info(f"Creating namespace: {self.namespace}")
        try:
            self.kube_cmd(["create", "namespace", self.namespace], namespaced=False)
        except RuntimeError:
            logging.warning("Could not create namespace")
            raise RuntimeError("Could not create namespace")

    def label(self, resource_type: str, name: str, labels: dict) -> None:
        """Label a resource with given label name and values

        Args:
            resource_type (str): type of the resource
            name (str): name of the resource
            labels (dict): labels to add to the resource
        """
        for key, value in labels.items():
            self.kube_cmd(["label", f"{resource_type}/{name}", f"{key}={value}"], namespaced=False)

    def create_secret_from_literals(self, name: str, literals: dict) -> None:
        """Create a kubernetes secret from literals dictionary

        Args:
            name (str): name of the secret
            literals (dict): key-secret dictionary
        """
        base_cmd = ["create", "secret", "generic", name]
        literals = [f"--from-literal={key}={item}" for key, item in literals.items()]
        self.kube_cmd(base_cmd + literals)

    def create_secret_from_file(self, name: str, path: Path) -> None:
        """Create a secret from a file

        Args:
            name (str): name of the secret
            path (Path): path to the text file
        """
        base_cmd = ["create", "secret", "generic", name, "--from-file", str(path)]
        self.kube_cmd(base_cmd)

    def create_tls_secret(self, secret_name: str, key: str, certificate: str) -> str:
        """Create a tls secret in the Kubernetes namespace

        Args:
            secret_name (str): name of the secret
            key (str): key path
            certificate (str): [certificate path]

        Returns:
            str: the result stdout during key creation
        """
        out, _ = self.kube_cmd(
            [
                "create",
                "secret",
                "tls",
                secret_name,
                "--key",
                str(key),
                "--cert",
                str(certificate),
            ]
        )
        return out

    def create_docker_secret(self, name: str, user: str, password: str, server: str) -> None:
        """Create a docker registry secret

        Args:
            name (str): name of the secret
            user (str): user name
            password (str): password
            server (str): server url (domain name or docker hub str)
        """
        self.kube_cmd(
            [
                "create",
                "secret",
                "docker-registry",
                name,
                "--docker-server",
                server,
                "--docker-username",
                user,
                "--docker-password",
                password,
            ]
        )

    def copy_secret(self, name: str, from_namespace: str) -> None:
        """Copy Kubernetes secret from another namespace

        Args:
            name (str): name of the secret
            from_namespace (str): where to copy the secret from
        """
        run_shell_command(
            f"kubectl get secret {name} --namespace={from_namespace} -oyaml | "
            f"sed -e 's@namespaces/{from_namespace}@namespaces/{self.namespace}@' | "
            f"sed -e 's@namespace: {from_namespace}@namespace: \"{self.namespace}\"@' | "
            f"kubectl apply --namespace={self.namespace} -f -",
            shell=True,
        )

    def get_secrets(self) -> List:
        """Get secrets in the current namespace

        Returns:
            List: secrets
        """
        out, _ = self.kube_cmd(["get", "secrets", "-o", "json"])
        secret_dict = json.loads(out)
        return secret_dict["items"]

    def get_services(self) -> List:
        """Get running services description

        Returns:
            List: list of deployment descriptors
        """
        out, _ = self.kube_cmd(["get", "svc", "-o", "json"])
        return json.loads(out)["items"]

    def get_deployments(self) -> List:
        """Get running deployments in namespace

        Returns:
            List: list of deployments
        """
        out, _ = self.kube_cmd(["get", "deployments.apps", "-o", "json"])
        return json.loads(out)["items"]

    def get_jobs(self) -> List:
        """Get jobs

        Returns:
            List: jobs
        """
        out, _ = self.kube_cmd(["get", "jobs.batch", "-o", "json"])
        return json.loads(out)["items"]

    def wait_and_get_ingress_public_ip(self, name: str) -> List:
        """Wait and get ingress public IP address of  a running deployment

        Args:
            name (str): name of the ingress

        Raises:
            RuntimeError: If ingress is not available after the service is up

        Returns:
            List: list of public IP addresses
        """
        while True:
            services = self.get_services()
            for svc in services:
                if svc["metadata"]["name"] == name and len(svc["status"]["loadBalancer"]) > 0:
                    ingress = svc["status"]["loadBalancer"]["ingress"]
                    public_ips = [x["ip"] for x in ingress]
                    if len(public_ips) == 0:
                        raise RuntimeError("No public IP found.")
                    return public_ips
            time.sleep(1)

    def wait_for_job_to_finish(self, name: str) -> bool:
        """Wait for a job to finish with successful result

        Args:
            name (str): name of the job

        Returns:
            bool: whether the job is successful
        """
        while True:
            jobs = self.get_jobs()
            for job in jobs:
                if (
                    job["metadata"]["name"] == name
                    and "completionTime" in job["status"]
                    and len(job["status"]["completionTime"]) == 20
                ):
                    return job["status"]["succeeded"] == 1
            time.sleep(1)

    def apply(self, path: Path, namespaced: bool = True) -> str:
        """Apply a yaml configuration

        Args:
            path (Path): yaml path or directory of descriptions
            namespaced (bool, optional): whether to deploy in a namespace or cluster-level. Defaults to True.

        Returns:
            str: the result of the command
        """
        cmd = ["apply", "-f", str(path)]
        out, _ = self.kube_cmd(cmd, namespaced=namespaced)
        return out

    def upload_file_as_configmap(self, name: str, path: Path) -> None:
        """Upload a file to the cluster as a config map

        Args:
            name (str): name of the config map
            path (Path): path to the file to upload
        """
        self.kube_cmd(["create", "configmap", name, "--from-file", str(path)])

    def get_logs(self, pod_name: str, since: str = None) -> str:
        """Get logs from a pod

        Args:
            pod_name (str): name of the pod
            since (str, optional): since in  a format like (20s, 15m). Defaults to None.

        Returns:
            str: the logs as a string
        """
        out, _ = self.kube_cmd(["logs", pod_name] + ([] if not since else [f"--since={since}"]))
        return out
