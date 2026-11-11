#!/bin/bash
# Exemplos vim-cmd via SSH no ESXi 6.7
# ssh root@192.168.0.125

# Listar todas as VMs (VMID, nome, arquivo, guest OS, versão)
vim-cmd vmsvc/getallvms

# Resumo de uma VM
vim-cmd vmsvc/get.summary <VMID>

# Ligar / desligar
vim-cmd vmsvc/power.on <VMID>
vim-cmd vmsvc/power.off <VMID>

# Estado de energia
vim-cmd vmsvc/power.getstate <VMID>

# Registrar VM copiada manualmente no datastore
vim-cmd solo/registervm /vmfs/volumes/datastore1/VPS-NOVO/VPS-NOVO.vmx "VPS-NOVO"

# Destruir VM
vim-cmd vmsvc/destroy <VMID>

# Listar datastores
vim-cmd hostsvc/datastore/listsummary
