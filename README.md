# WMT Desktop - Workstation Manager Tools

Uma aplicação desktop moderna para gerenciamento centralizado de workstations, construída com **Tauri**, **React**, **TypeScript**, **Python** e **PowerShell**.

## 🎯 Funcionalidades

- **Dashboard**: Visão geral do sistema com KPIs e atividades recentes
- **Monitor**: Monitoramento em tempo real de workstations
- **Applications**: Gerenciamento de aplicações instaladas
- **Backup**: Gerenciamento de backups de sistema
- **Admin Users**: Gerenciamento de usuários e permissões
- **Account**: Configurações de perfil e segurança

## 🏗️ Arquitetura

```
wmt-desktop/
├── client/                 # Frontend React + TypeScript
│   ├── src/
│   │   ├── pages/         # Páginas da aplicação
│   │   ├── components/    # Componentes reutilizáveis
│   │   ├── hooks/         # Custom hooks
│   │   ├── contexts/      # React contexts
│   │   └── lib/           # Utilitários
│   └── index.html
├── backend/               # Backend FastAPI + Python
│   ├── app/
│   │   ├── main.py       # Aplicação principal
│   │   ├── routes.py     # Rotas adicionais
│   │   ├── auth.py       # Autenticação
│   │   ├── powershell.py # Integração PowerShell
│   │   ├── audit.py      # Auditoria
│   │   └── logger.py     # Logging
│   ├── scripts/
│   │   └── remote_operations.ps1  # Scripts PowerShell
│   ├── main.py           # Entry point
│   └── requirements.txt   # Dependências Python
├── src-tauri/            # Configuração Tauri
│   ├── src/
│   │   ├── main.rs       # Entry point Rust
│   │   ├── lib.rs        # Biblioteca Rust
│   │   └── commands.rs   # Comandos Tauri
│   └── Cargo.toml        # Dependências Rust
└── package.json          # Dependências Node.js
```

## 🚀 Início Rápido

### Pré-requisitos

- Node.js 18+
- Python 3.11+
- Rust (para compilação Tauri)
- PowerShell 5.0+ (Windows)

### Instalação

1. **Clonar o repositório**
```bash
git clone <repository-url>
cd wmt-desktop
```

2. **Instalar dependências Node.js**
```bash
pnpm install
```

3. **Instalar dependências Python**
```bash
cd backend
pip install -r requirements-dev.txt
cd ..
```

### Desenvolvimento

#### Terminal 1 - Backend FastAPI
```bash
cd backend
python main.py
```

O backend estará disponível em `http://localhost:8000`

#### Terminal 2 - Frontend React
```bash
pnpm dev
```

O frontend estará disponível em `http://localhost:5173`

#### Terminal 3 - Tauri (opcional)
```bash
pnpm dev:tauri
```

### Build para Desktop

```bash
pnpm build:tauri
```

Os executáveis serão gerados em `src-tauri/target/release/`

### Build/Migração em Servidor Novo

Use este checklist quando precisar mover o build para outra máquina/servidor Windows.

#### 1. Instalar pré-requisitos

```powershell
node --version
pnpm --version
cargo --version
python --version
```

Se algum comando não existir, instale:

- Node.js 18+
- pnpm/Corepack
- Rust/Cargo
- Python 3.11+
- WiX Toolset 3.14 ou cache local do WiX, conforme abaixo

#### 2. Instalar dependências do projeto

```powershell
pnpm install

cd backend
pip install -r requirements-dev.txt
cd ..
```

#### 3. Preparar a chave do updater

O build com `createUpdaterArtifacts: true` precisa da chave privada para gerar o `.sig`.

Confirme que existe:

```text
secrets\wmt-updater.key
secrets\wmt-updater.key.pub
```

Antes de buildar manualmente, configure:

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = "C:\wmt-desktop\secrets\wmt-updater.key"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
```

O script `scripts\build-and-release.ps1` já faz isso automaticamente quando encontra `secrets\wmt-updater.key`.

#### 4. Preparar cache local do WiX

Em redes corporativas, o Tauri pode falhar ao baixar o WiX do GitHub com:

```text
failed to bundle project: `io: invalid peer certificate: UnknownIssuer`
```

Para evitar esse download, o projeto usa `bundle.useLocalToolsDir: true` em `src-tauri\tauri.conf.json` e espera o WiX em:

```text
src-tauri\target\.tauri\WixTools314
```

Se a máquina já tiver o cache global do Tauri, copie assim:

```powershell
New-Item -ItemType Directory -Force -Path .\src-tauri\target\.tauri\WixTools314 | Out-Null
Copy-Item -Path "$env:LOCALAPPDATA\tauri\wix314-binaries\*" -Destination .\src-tauri\target\.tauri\WixTools314 -Recurse -Force
```

Se o cache global ainda não existir, instale/extraia o WiX 3.14 e copie os binários equivalentes para `src-tauri\target\.tauri\WixTools314`. O diretório precisa conter arquivos como:

```text
candle.exe
light.exe
wix.dll
WixUIExtension.dll
WixUtilExtension.dll
```

#### 5. Build manual

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = "C:\wmt-desktop\secrets\wmt-updater.key"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
pnpm build:tauri
```

Artefatos esperados:

```text
src-tauri\target\release\wmt-desktop.exe
src-tauri\target\release\bundle\msi\WMT Desktop*.msi
src-tauri\target\release\bundle\msi\WMT Desktop*.msi.sig
```

#### 6. Build/release recomendado

Para gerar release, publicar `latest.json`/`latest-debug.json` e copiar artefatos:

```powershell
.\scripts\build-and-release.ps1 -Channel prod -Type patch -BackendUrl "https://SEU-SERVIDOR"
```

Build debug lado a lado:

```powershell
.\scripts\build-and-release.ps1 -Channel debug -Type patch -BackendUrl "https://SEU-SERVIDOR"
```

## 📚 Estrutura de Rotas

### Autenticação
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Obter usuário atual

### Dashboard
- `GET /api/dashboard` - Dados do dashboard

### Workstations
- `GET /api/workstations` - Listar workstations
- `GET /api/workstations/{id}` - Detalhes da workstation
- `GET /api/workstations/{id}/details` - Informações detalhadas
- `POST /api/workstations/{id}/reboot` - Reiniciar
- `POST /api/workstations/{id}/shutdown` - Desligar

### Aplicações
- `GET /api/applications/{wk_id}` - Listar aplicações

### Backup
- `GET /api/backup/jobs` - Listar jobs de backup
- `POST /api/backup/jobs` - Criar novo backup

### Usuários
- `GET /api/users` - Listar usuários
- `POST /api/users` - Criar usuário
- `PUT /api/users/{id}` - Atualizar usuário
- `DELETE /api/users/{id}` - Deletar usuário

### Conta
- `GET /api/account/profile` - Perfil do usuário
- `POST /api/account/change-password` - Alterar senha

## 🔐 Autenticação

O sistema usa autenticação baseada em sessão com suporte a RBAC (Role-Based Access Control).

**Roles disponíveis:**
- `admin` - Acesso total ao sistema
- `operator` - Acesso a operações gerenciais
- `viewer` - Acesso apenas leitura

Não existem credenciais padrão. Para criar o primeiro administrador local,
defina `WMT_BOOTSTRAP_ADMIN_PASSWORD` com uma senha exclusiva de pelo menos
12 caracteres antes da primeira inicialização. Remova a variável após confirmar
o acesso. Em ambientes com SSO, o primeiro usuário também pode ser provisionado
pelas regras de grupos/usuários configuradas.

## 🔧 Configuração

### Variáveis de Ambiente

Defina as variáveis no ambiente do processo ou serviço que executa o backend:

```env
WMT_BOOTSTRAP_ADMIN_USERNAME=admin
WMT_BOOTSTRAP_ADMIN_PASSWORD=uma-senha-inicial-exclusiva
WMT_BOOTSTRAP_ADMIN_EMAIL=wmt-admin@empresa.local
WMT_STATE_DB_PATH=C:\ProgramData\WMT\state.db

WMT_SSO_ENABLED=true
WMT_SSO_DESKTOP_FALLBACK=true
WMT_SSO_CLIENT_IP_FALLBACK=true
WMT_SSO_TRUSTED_PROXY_IPS=127.0.0.1,::1
WMT_SSO_ALLOWED_GROUPS=CN=WMT-Users,OU=Groups,DC=empresa,DC=local
WMT_SSO_ADMIN_GROUPS=CN=WMT-Admins,OU=Groups,DC=empresa,DC=local
WMT_SSO_ADMIN_USERS=usuario.admin@empresa.local
WMT_SSO_DEFAULT_ROLE=viewer

WMT_LOGIN_RATE_LIMIT_MAX_ATTEMPTS=5
WMT_LOGIN_RATE_LIMIT_WINDOW_SECONDS=300
WMT_MAX_CONCURRENT_REMOTE_JOBS=8
WMT_MAX_CONCURRENT_UPDATE_JOBS=4
WMT_MAX_CONCURRENT_BACKUP_JOBS=2
```

SSO e seus fallbacks ficam desativados por padrão e devem ser habilitados
explicitamente. Quando SSO está ativo, `WMT_SSO_ALLOWED_GROUPS` é obrigatório;
uma configuração vazia é recusada. `WMT_SSO_DEBUG_ENABLED` permanece
desativada.

Use `WMT_SSO_ADMIN_GROUPS` para promover membros de grupos do AD e
`WMT_SSO_ADMIN_USERS` para exceções nominais, separadas por vírgula ou
ponto e vírgula. Sem uma dessas regras, os usuários SSO recebem
`WMT_SSO_DEFAULT_ROLE` (por padrão, `viewer`). Papéis atribuídos manualmente
na tela administrativa têm precedência sobre as regras SSO.

As origens CORS de produção devem ser adicionadas explicitamente em
`WMT_CORS_ORIGINS`. Localhost só é aceito automaticamente com `WMT_DEV=true`.

Veja [Login Windows sem IIS](docs/sso-windows-without-iis.md) para os modos
local (`whoami`) e servidor central (WMI/CIM pela conexão direta).

## 📝 Scripts PowerShell

Os scripts PowerShell estão localizados em `backend/scripts/`:

### remote_operations.ps1

Executa operações remotas em workstations:

```powershell
# Obter informações do sistema
.\remote_operations.ps1 -ComputerName "WK-001" -Operation "GetInfo"

# Reiniciar workstation
.\remote_operations.ps1 -ComputerName "WK-001" -Operation "Reboot" -Delay 60

# Desligar workstation
.\remote_operations.ps1 -ComputerName "WK-001" -Operation "Shutdown"

# Listar aplicações instaladas
.\remote_operations.ps1 -ComputerName "WK-001" -Operation "GetApplications"

# Obter atualizações pendentes
.\remote_operations.ps1 -ComputerName "WK-001" -Operation "GetUpdates"
```

## 🧪 Testes

A lista consolidada de documentos está em
[Documentação do WMT](docs/README.md).

### Backend central ou sidecar

O release corporativo usa `-BackendMode central` e não inicia Python na
estação. Uma edição local pode usar `-BackendMode sidecar`, que empacota o
FastAPI em um executável independente.

Veja [Runtime do backend](docs/backend-runtime.md).

### Testar Backend
```bash
python -m unittest discover -s backend/tests -v
```

### Testar Frontend
```bash
pnpm test
```

A matriz central de permissões e o layout autenticado estão documentados em
[Autorização no frontend](docs/frontend-authorization.md).

## 📦 Dependências Principais

### Frontend
- React 19
- TypeScript
- Tailwind CSS 4
- shadcn/ui
- Wouter (routing)
- Sonner (toasts)
- Lucide React (ícones)

### Backend
- FastAPI
- Pydantic
- SQLite nativo
- Uvicorn

### Desktop
- Tauri 2
- Rust

## 🐛 Troubleshooting

### Erro: "Cannot find module '@tauri-apps/api'"
```bash
pnpm install
```

### Erro: "Backend não conecta"

Verifique os endpoints e a tarefa agendada:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Get-ScheduledTask -TaskName "WMT Backend"
Get-ScheduledTaskInfo -TaskName "WMT Backend"
```

O backend está pronto somente quando `/health/ready` retorna `status=ready`.
Os logs ficam em `backend\data\logs\backend.log` na instalação do projeto.

Para reiniciar, use a tarefa registrada, não execute `python main.py` em uma
segunda janela:

```powershell
Stop-ScheduledTask -TaskName "WMT Backend"
Start-ScheduledTask -TaskName "WMT Backend"
```

Depois confirme que existe apenas um listener na porta 8000:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

### Erro: login SSO diz que o host está inacessível

No modo central sem identidade encaminhada pelo IIS, o backend identifica o
usuário consultando a estação de origem. A conta da tarefa `WMT Backend` deve
ter acesso remoto às workstations, e WMI/RPC ou Terminal Services RPC precisa
estar liberado na rede.

```powershell
Test-Connection 10.0.0.10 -Count 2
quser /server:10.0.0.10
Get-CimInstance -ComputerName 10.0.0.10 -ClassName Win32_ComputerSystem
```

Proxies Windows podem enviar `X-Forwarded-For` no formato
`10.0.0.10:porta-temporaria`. O backend normaliza esse formato antes da
consulta. A porta observada, como `60116`, não é uma porta de serviço da
workstation e não deve ser usada nos testes.

Prefira IIS com Windows Authentication encaminhando `X-Remote-User` (ou
`X-IIS-WinAuth-User`); isso evita depender da consulta remota por IP. Veja
[Configuração do IIS com Windows Authentication](docs/iis-windows-auth-setup.md).

### Usuário SSO entrou como `viewer`, mas deveria ser `admin`

Confira se as regras administrativas estão disponíveis para o processo que
executa o backend:

```powershell
[Environment]::GetEnvironmentVariable("WMT_SSO_ADMIN_GROUPS", "Machine")
[Environment]::GetEnvironmentVariable("WMT_SSO_ADMIN_USERS", "Machine")
```

Após corrigir as variáveis, reinicie a tarefa `WMT Backend` e faça logout/login
para renovar a sessão. Não use `WMT_SSO_DEFAULT_ROLE=admin`: configure grupos,
usuários nominais ou atribua o papel manualmente pela administração do WMT.

### Erro: "PowerShell scripts não executam"
Verificar permissões de execução:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 📄 Licença

MIT

## 👥 Contribuindo

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📞 Suporte

Para suporte, abra uma issue no repositório.

---

**Desenvolvido com ❤️ usando Tauri, React e TypeScript**
