import os
from pathlib import Path

from nnstorm_cloud.azure.api import AzureApi
from nnstorm_cloud.azure.keyvault import AzureKeyVault
from nnstorm_cloud.azure.manager import AzureManager

auth = Path(os.environ["AZURE_AUTH_LOCATION"])


def test_api_init():
    api = AzureApi(auth)


def test_object_id_fetch():
    api = AzureApi(auth)
    api.get_object_id()


def test_kv_init():
    kv = AzureKeyVault("test-kv-1", auth)


def test_manager_init():
    mgr = AzureManager("test-manager-0", auth_path=auth, location="westeurope", create_rsg=False)


def test_storage_account_credentials():
    mgr = AzureManager("test-manager-0", auth_path=auth, location="westeurope", create_rsg=False)
    mgr.check_storage_available("abc")


def test_manager_rsg_create():
    mgr = AzureManager("test-manager-1", auth_path=auth, location="westeurope")
    mgr.set_async(True)
    mgr.delete_rsg()


def test_kv_available():
    kv = AzureKeyVault("nnstorm-av-test-kv-1", auth)
    assert kv.check_name_available()


def test_kv_full_lifecycle():
    mgr = AzureManager("test-manager-2", auth_path=auth, location="westeurope")

    kv = AzureKeyVault("nnstorm-av-test-kv-3", auth)
    assert not kv.exists
    kv.create_keyvault(rsg=mgr.rsg, location=mgr.get_location(), soft_delete=True)
    assert kv.exists
    kv.grant_access(rsg=mgr.rsg)
    kv.set_secret("test1", "x")
    assert kv.get_secret("test1") == "x"
    kv.delete_secret("test1")
    kv.delete_keyvault(rsg=mgr.rsg, location=mgr.get_location())
    assert not kv.exists
    kv.create_keyvault(rsg=mgr.rsg, location=mgr.get_location(), soft_delete=True)
    assert kv.exists
    kv.delete_keyvault(rsg=mgr.rsg, location=mgr.get_location())
    assert not kv.exists
    mgr.set_async(True)
    mgr.delete_rsg()
