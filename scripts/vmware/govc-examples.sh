#!/bin/bash
# Exemplos govc para ESXi 6.7 standalone
# Instale: https://github.com/vmware/govmomi/releases

: "${GOVC_URL:?Defina GOVC_URL no ambiente antes de executar}"
export GOVC_URL
export GOVC_INSECURE=true

# Listar VMs
govc ls /ha-datacenter/vm/

# Clonar template
govc vm.clone -vm="VPS MODELO" -on=false -ds=datastore1 "VPS-TESTE"

# Reconfigurar recursos
govc vm.change -vm="VPS-TESTE" -c 2 -m 4096

# Ligar
govc vm.power -on "VPS-TESTE"

# Info
govc vm.info "VPS-TESTE"
