"""NNstorm utils for Azure deployment"""
import logging
import os
import subprocess
from typing import List, Optional, Tuple, Union


def run_shell_command(
    command_arg_list: Union[List, str],
    show_info: bool = False,
    shell: bool = False,
    log: Optional[logging.Logger] = None,
    poll: bool = True,
) -> Tuple[str, str]:
    """Runs shell command in host shell and returns output and error response

    Args:
        command_arg_list (Union[List, str]): List of command line args or str command to run (if shell=true)
        show_info (bool, optional): log with info level. Defaults to False.
        shell (bool, optional): run in shell mode (if arg_list is list). Defaults to False.
        log (Optional[logging.Logger], optional): Logger object to use. Defaults to None.
        poll (bool): whether to poll the process or return its stdout as a whole

    Raises:
        RuntimeError: If process did not return with 0

    Returns:
        Tuple[str, str]: standard output and standard error as str
    """
    if not log:
        log = logging.getLogger("shell")

    cmd = command_arg_list if isinstance(command_arg_list, str) else " ".join(command_arg_list)
    log.debug(f"Running shell script: {cmd}")

    process = subprocess.Popen(command_arg_list, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if poll:
        outs = []
        while True:
            output = process.stdout.readline()

            log_fn = log.info if show_info else log.debug

            if len(output) > 0:
                try:
                    s = output.decode("utf-8").strip()
                    outs.append(s)
                    log_fn(outs[-1])
                except UnicodeDecodeError:
                    log.warning(f"Could not decode {output} with utf-8")

            if process.poll() is not None:
                break

    process.wait()
    stdout, stderr = process.communicate()

    try:
        stdout = stdout.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        stderr = stderr.decode("utf-8")
    except UnicodeDecodeError:
        pass

    if poll:
        stdout = "\n".join(outs)

    if process.returncode != 0:
        log.warning(stdout)
        log.error(stderr)
        raise RuntimeError("Shellscript exited with non-0 exit code!")

    return stdout, stderr


def get_environment_variable(name: str) -> str:
    """Get environment variable from the parent shell

    Args:
        name (str): name of the environment variable

    Raises:
        RuntimeError: If env var does not exist or empty

    Returns:
        str: the value of the environment variable
    """
    try:
        env_var = os.environ[name]
    except KeyError:
        raise RuntimeError(f"'{name}' env var does not exist.")
    if len(env_var) == 0:
        raise RuntimeError(f"'{name}' env var is empty.")
    return env_var
