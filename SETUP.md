# WMT Desktop - Setup e Instalação

## Visão Geral

WMT Desktop é uma aplicação desktop multiplataforma para gerenciamento de workstations, construída com **Tauri + React + TypeScript** no frontend e **FastAPI + Python** no backend.

## Pré-requisitos

### Windows
- **Node.js** 18+ (com npm ou pnpm)
- **Python** 3.8+ (com pip)
- **Rust** (para compilar Tauri)
- **Visual Studio Build Tools** (para compilação C++)
- **PowerShell** 7+ (para scripts de gerenciamento remoto)

### macOS
- **Node.js** 18+ (com npm ou pnpm)
- **Python** 3.8+ (com pip)
- **Rust** (para compilar Tauri)
- **Xcode Command Line Tools**: `xcode-select --install`

### Linux
- **Node.js** 18+ (com npm ou pnpm)
- **Python** 3.8+ (com pip)
- **Rust** (para compilar Tauri)
- **Build essentials**: `sudo apt-get install build-essential libssl-dev`

## Instalação

### 1. Clonar o repositório

```bash
git clone <repository-url>
cd wmt-desktop
```

### 2. Instalar dependências Node.js

```bash
# Usando pnpm (recomendado)
pnpm install

# Ou usando npm
npm install
```

### 3. Instalar dependências Python

```bash
# Criar virtual environment
python -m venv backend/venv

# Ativar virtual environment
# Windows:
backend\venv\Scripts\activate
# macOS/Linux:
source backend/venv/bin/activate

# Instalar dependências
pip install -r backend/requirements.txt
```

### 4. Configurar variáveis de ambiente

```powershell
# Bootstrap local opcional (mínimo de 12 caracteres)
$env:WMT_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:WMT_BOOTSTRAP_ADMIN_PASSWORD = "uma-senha-inicial-exclusiva"
$env:WMT_BOOTSTRAP_ADMIN_EMAIL = "wmt-admin@empresa.local"

# Persistência; o padrão é backend/data/state.db
$env:WMT_STATE_DB_PATH = "C:\ProgramData\WMT\state.db"

# Cookies de produção (HTTPS)
$env:WMT_SESSION_COOKIE_SECURE = "true"
$env:WMT_SESSION_COOKIE_SAMESITE = "none"
$env:WMT_ALLOW_BEARER_AUTH = "false"

# Operações remotas, quando necessárias
$env:REMOTE_ADMIN_USER = "DOMINIO\conta-servico"
$env:REMOTE_ADMIN_PASS = "segredo-fornecido-pelo-cofre"
```

Não há usuário ou senha padrão. Remova a variável de bootstrap depois de
confirmar o primeiro acesso.

## Desenvolvimento

### Modo Desenvolvimento (com Tauri)

```bash
# Terminal 1: Iniciar o servidor de desenvolvimento Vite
pnpm dev

# Terminal 2: Iniciar a aplicação Tauri
pnpm dev:tauri
```

Isso abrirá a aplicação desktop com hot-reload do frontend.

### Modo Desenvolvimento (sem Tauri - apenas web)

```bash
# Terminal 1: Iniciar o servidor Vite
pnpm dev

# Terminal 2: Iniciar o backend FastAPI
cd backend
source venv/bin/activate  # ou backend\venv\Scripts\activate no Windows
python main.py
```

Acesse http://localhost:5173 no navegador.

## Build para Produção

### Build da aplicação desktop

```bash
# Compilar para o seu sistema operacional
pnpm build:tauri

# Resultado:
# Windows: src-tauri/target/release/WMT.exe
# macOS: src-tauri/target/release/WMT.app
# Linux: src-tauri/target/release/WMT
```

### Build para múltiplas plataformas

```bash
# Windows (x86_64)
pnpm build:tauri --target x86_64-pc-windows-msvc

# macOS (Intel)
pnpm build:tauri --target x86_64-apple-darwin

# macOS (Apple Silicon)
pnpm build:tauri --target aarch64-apple-darwin

# Linux (x86_64)
pnpm build:tauri --target x86_64-unknown-linux-gnu
```

## Estrutura do Projeto

```
wmt-desktop/
├── client/                    # Frontend React + TypeScript
│   ├── src/
│   │   ├── pages/            # Páginas (Dashboard, Monitor, etc.)
│   │   ├── components/       # Componentes reutilizáveis
│   │   ├── hooks/            # Custom hooks (useApi, useAuth)
│   │   ├── contexts/         # React contexts
│   │   ├── lib/              # Utilitários
│   │   ├── App.tsx           # Componente raiz
│   │   └── main.tsx          # Entry point
│   ├── index.html
│   └── public/
├── backend/                   # Backend FastAPI + Python
│   ├── app/
│   │   ├── main.py           # Composição da aplicação FastAPI
│   │   ├── schemas.py        # Contratos Pydantic da API
│   │   ├── core/             # Configuração, segurança e validadores
│   │   ├── repositories/     # Persistência do estado
│   │   ├── services/         # Regras operacionais por domínio
│   │   ├── runtime.py        # Fachada temporária de compatibilidade
│   │   └── api/              # Rotas separadas por domínio
│   │       ├── auth.py
│   │       ├── backup.py
│   │       ├── diagnostics.py
│   │       └── ...
│   ├── scripts/              # Scripts PowerShell
│   │   ├── consulta.ps1
│   │   ├── applications.ps1
│   │   ├── backup.ps1
│   │   └── ...
│   ├── data/                 # SQLite e artefatos locais
│   ├── main.py               # Entry point
│   ├── requirements.txt
│   └── venv/                 # Virtual environment
├── src-tauri/                # Configuração Tauri
│   ├── src/
│   │   ├── main.rs           # Entry point Rust
│   │   ├── commands.rs       # Comandos Tauri
│   │   └── lib.rs
│   ├── tauri.conf.json       # Config Tauri
│   └── Cargo.toml
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Configuração de Rede

### Comunicação Frontend ↔ Backend

- **Frontend**: Roda em `http://localhost:5173` (dev) ou empacotado no Tauri
- **Backend**: Roda em `http://127.0.0.1:8000` (localhost apenas)
- **CORS**: Configurado para aceitar apenas localhost

### Firewall

- Nenhuma porta é exposta externamente
- Comunicação apenas local (127.0.0.1)
- Seguro para uso em redes corporativas

## Troubleshooting

### Erro: "Backend is not responding"

```bash
# Verificar se o backend está rodando
curl http://localhost:8000/health/ready

# Se não funcionar, iniciar manualmente:
cd backend
source venv/bin/activate
python main.py
```

### Erro: "PowerShell script not found"

- Verificar se os scripts estão em `backend/scripts/`
- Verificar permissões: `ls -la backend/scripts/`
- No Windows, pode ser necessário executar: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned`

### Erro ao compilar Tauri

```bash
# Limpar cache Rust
cargo clean

# Reinstalar dependências
pnpm install
cargo build --release
```

## Segurança

1. **Autenticação**: Sessão opaca em cookie `HttpOnly` com proteção CSRF
2. **Autorização**: RBAC (Role-Based Access Control)
3. **Comunicação**: HTTPS no modo central; HTTP apenas em loopback no sidecar
4. **Credenciais**: Use variáveis de ambiente, nunca commite `.env`
5. **Logs**: Auditoria persistida e logs do sidecar no diretório da aplicação
## Login Windows sem IIS (Produção)

O aplicativo desktop tenta primeiro restaurar uma sessão existente e depois
identifica automaticamente o usuário Windows:

- backend local: executa `whoami /upn` na sessão iniciada pelo Tauri;
- backend central: consulta via WMI/CIM a sessão da estação identificada pelo
  endereço IP direto da conexão.

```powershell
[Environment]::SetEnvironmentVariable('WMT_SSO_ENABLED', 'true', 'Machine')
[Environment]::SetEnvironmentVariable('WMT_SSO_DESKTOP_FALLBACK', 'true', 'Machine')
[Environment]::SetEnvironmentVariable('WMT_SSO_CLIENT_IP_FALLBACK', 'true', 'Machine')
```

Veja [Login Windows sem IIS](docs/sso-windows-without-iis.md) para os requisitos
de rede, firewall e permissões.

## Configuração opcional com IIS + Windows Authentication

Caso o ambiente use IIS, ele também pode funcionar como proxy reverso com
autenticação Windows:

### Documentação Completa

Veja [docs/iis-windows-auth-setup.md](docs/iis-windows-auth-setup.md) para instruções detalhadas.

### Instalação Rápida (PowerShell)

```powershell
# Como Administrator
cd c:\Users\...\wmt-desktop

# 1. Configurar IIS
.\scripts\configure-iis-windows-auth.ps1 -SiteName "WMT" -BackendUrl "http://127.0.0.1:8000"

# 2. Configurar variáveis de ambiente
[Environment]::SetEnvironmentVariable('WMT_SSO_ENABLED', 'true', 'Machine')
[Environment]::SetEnvironmentVariable('WMT_SSO_TRUSTED_PROXY_IPS', '127.0.0.1,::1', 'Machine')

# 3. Testar configuração
.\scripts\test-iis-windows-auth.ps1 -SiteName "WMT"
```

### Fluxo SSO

```
1. Usuário acessa https://wmt.empresa.local
2. IIS responde com WWW-Authenticate: Negotiate
3. Navegador envia credenciais Windows (Kerberos/NTLM)
4. IIS valida no Active Directory
5. IIS reescreve para http://127.0.0.1:8000 com header X-Remote-User
6. Backend FastAPI cria a sessão e devolve cookie `HttpOnly`
7. Frontend usa o cookie e um token CSRF mantido apenas em memória
```

### Variáveis de Ambiente Essenciais

```powershell
$env:WMT_SSO_ENABLED = "true"
$env:WMT_SSO_TRUSTED_PROXY_IPS = "127.0.0.1,::1"
$env:WMT_SSO_ALLOWED_GROUPS = "CN=WMT-Users,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_ADMIN_GROUPS = "CN=WMT-Admins,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_DEFAULT_ROLE = "viewer"
```
## Performance

- **Frontend**: React 19 com otimizações de renderização
- **Backend**: FastAPI com cache em memória
- **Polling**: Configurável via `refetchInterval` nos hooks
- **Tauri**: Empacotamento eficiente com Rust

## Contribuindo

1. Criar branch para sua feature: `git checkout -b feature/sua-feature`
2. Commit suas mudanças: `git commit -am 'Add feature'`
3. Push para o branch: `git push origin feature/sua-feature`
4. Criar Pull Request

## Licença

MIT

## Suporte

Para problemas ou dúvidas, abra uma issue no repositório.
