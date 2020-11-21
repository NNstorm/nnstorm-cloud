# NNstorm cloud

## Install

Install latest stable release from PyPI:

```bash
pip install nnstorm-cloud
```

## Set up development version

```bash
git clone https://github.com/NNstorm/nnstorm-cloud.git
cd nnstorm-cloud
pip install -e .
```

## Set up for usage

Create Azure ssh keys:

```bash
ssh-keygen -t rsa -b 4096 -f $HOME/.ssh/azure_key.pem -P ""
```

Set these in `$HOME/.profile` or source it in your shell's `.rc` file or just in the current shell.

```bash
export NNSTORM_AZURE_AUTH_LOCATION=${HOME}/.azure/NNSTORM_azure_credentials.json
export NNSTORM_AZURE_KEYVAULT=<your azure keyvault name>
```

Run this to store service credentials locally:

```bash
az ad sp create-for-rbac --sdk-auth > $NNSTORM_AZURE_AUTH_LOCATION
client_id=$(cat $NNSTORM_AZURE_AUTH_LOCATION | python3 -c "import sys, json; print(json.load(sys.stdin)['clientId'])")
az keyvault set-policy -n $NNSTORM_AZURE_KEYVAULT --spn ${client_id} --secret-permissions delete get list set --key-permissions create decrypt delete encrypt get list unwrapKey wrapKey
```
