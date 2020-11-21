ssh xxxx@zzz.eastus.cloudapp.azure.com "sudo waagent -deprovision+user -force"
az vm deallocate --resource-group train --name small-vm
az vm generalize --resource-group train --name small-vm

az image create \
    --resource-group train \
    --name deep_image_v5 \
    --source small-vm
