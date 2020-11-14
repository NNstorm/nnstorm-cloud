import os
from pathlib import Path

import pytest
from nnstorm_cloud.azure.keyvault import AzureKeyVault


def test_kv():
    auth = Path(os.environ["INTLAND_AZURE_AUTH_LOCATION"])
    kv = AzureKeyVault("test-kv-1", auth)
    print("name available", kv.check_name_available())
