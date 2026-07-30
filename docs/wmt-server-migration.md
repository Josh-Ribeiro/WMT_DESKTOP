# Migracao do WMT para servidor Windows

Este guia leva o WMT para um computador/servidor central, com backend FastAPI rodando em background e IIS na frente com Windows Authentication.

## Modelo recomendado

- Servidor Windows no dominio.
- Conta de servico AD para rodar o backend, por exemplo `GROUP\svc_wmt`.
- Essa conta deve ter permissao administrativa nas workstations quando for executar lookup, remote actions, diagnostic, SCCM e backup.
- IIS publica o WMT em `http://NOME-SERVIDOR` ou `https://wmt.empresa.local`.
- Os desktops/usuarios acessam o WMT pelo IIS ou instalam MSI apontando para esse mesmo servidor.

## Pre-requisitos no servidor

- Windows Server ou Windows 10/11 corporativo.
- PowerShell como Administrador.
- Python 3.11+ instalado e no PATH.
- IIS URL Rewrite e Application Request Routing para proxy reverso.
- Node.js + pnpm somente se voce quiser buildar o frontend no proprio servidor.

O script instala os recursos nativos do IIS. URL Rewrite/ARR sao extensoes externas; o script tenta instalar via `winget` com `-InstallIisExtensions`, mas em rede corporativa pode ser necessario instalar manualmente.

## Copiar o WMT para o servidor

No computador atual:

```powershell
pnpm build
```

Copie a pasta do projeto para o servidor, por exemplo:

```powershell
robocopy C:\caminho\wmt-desktop \\SERVIDOR\C$\Temp\wmt-desktop /MIR /XD node_modules src-tauri\target .venv .git
```

No servidor, abra PowerShell como Administrador dentro da pasta copiada:

```powershell
cd C:\Temp\wmt-desktop
```

## Instalar no servidor

Exemplo com URL por hostname:

```powershell
.\scripts\install-wmt-server.ps1 `
  -PublicUrl "http://SERVIDOR" `
  -ServiceAccount "GROUP\svc_wmt" `
  -SsoDefaultRole "viewer"
```

Exemplo com DNS dedicado:

```powershell
.\scripts\install-wmt-server.ps1 `
  -PublicUrl "https://wmt.empresa.local" `
  -Protocol https `
  -SitePort 443 `
  -HostHeader "wmt.empresa.local" `
  -ServiceAccount "GROUP\svc_wmt" `
  -SsoAllowedGroups "CN=WMT-Users,OU=Groups,DC=group,DC=pirelli,DC=com" `
  -SsoAdminGroups "CN=WMT-Admins,OU=Groups,DC=group,DC=pirelli,DC=com" `
  -SsoOperatorGroups "CN=WMT-Operators,OU=Groups,DC=group,DC=pirelli,DC=com"
```

O script vai pedir a senha da conta de servico e registrar uma tarefa agendada chamada `WMT Backend`.

## Validar

No servidor:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Get-ScheduledTask -TaskName "WMT Backend"
```

No navegador:

```text
http://SERVIDOR
```

Se aparecer erro do IIS relacionado a `rewrite`, instale IIS URL Rewrite + ARR e rode o script novamente.

## Build do MSI apontando para o servidor

Depois do servidor pronto, gere o instalador desktop apontando para a URL central:

```powershell
.\scripts\build-and-release.ps1 -Type patch -BackendUrl "https://SERVIDOR"
```

Com HTTPS/DNS:

```powershell
.\scripts\build-and-release.ps1 -Type patch -BackendUrl "https://wmt.empresa.local"
```

O MSI final fica em `releases\<versao>\`.

## Migrar dados atuais

O instalador copia `backend\data`, incluindo:

- usuarios locais e SSO cache
- historico de jobs
- auditoria
- updates publicados
- configuracoes

Se voce ja instalou no servidor e quer migrar dados depois, pare a tarefa `WMT Backend`, copie `backend\data` para `C:\WMT\backend\data` e inicie a tarefa novamente.

```powershell
Stop-ScheduledTask -TaskName "WMT Backend"
robocopy C:\Temp\wmt-desktop\backend\data C:\WMT\backend\data /MIR
Start-ScheduledTask -TaskName "WMT Backend"
```

## Observacoes importantes

- Para remote actions e SCCM, a conta do backend precisa de permissao administrativa nos hosts.
- Para backup, a tela agora aceita credenciais AD do operador e usa essas credenciais nas conexoes SMB/robocopy.
- Para SSO sem prompt, configure Intranet Zone/Windows Integrated Authentication nos navegadores dos usuarios.
- Para HTTPS, adicione o certificado no binding do IIS depois que o site for criado.
