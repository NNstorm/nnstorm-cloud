import os
from pathlib import Path

import pytest
from nnstorm_cloud.azure.api import AzureApi
from nnstorm_cloud.azure.keyvault import AzureKeyVault
from nnstorm_cloud.azure.manager import AzureManager

auth = Path(os.environ["INTLAND_AZURE_AUTH_LOCATION"])


def test_api_init():
    api = AzureApi(auth)


def test_kv_init():
    kv = AzureKeyVault("test-kv-1", auth)


def test_manager_init():
    mgr = AzureManager("test-manager-1", auth_path=auth, location="westeurope")
    mgr.set_async(True)
    mgr.delete_rsg()


def test_kv_available():
    kv = AzureKeyVault("nnstorm-av-test-kv-1", auth)
    assert kv.check_name_available()


def test_kv_full_lifecycle():
    mgr = AzureManager("test-manager-2", auth_path=auth, location="westeurope")
    kv = AzureKeyVault("nnstorm-av-test-kv-3", auth)
    kv.create_keyvault(rsg=mgr.rsg, location=mgr.get_location(), soft_delete=True)
    kv.grant_access(rsg=mgr.rsg)
    kv.set_secret("test1", "x")
    assert kv.get_secret("test1") == "x"
    kv.delete_secret("test1")
    kv.delete_keyvault(rsg=mgr.rsg, location=mgr.get_location())
    mgr.set_async(True)
    mgr.delete_rsg()
