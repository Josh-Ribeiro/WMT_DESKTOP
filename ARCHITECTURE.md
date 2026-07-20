# WMT Desktop - Arquitetura de Conversão

## Visão Geral

Transformação de aplicação web FastAPI + Jinja2 para aplicação desktop multiplataforma usando **Tauri + React + TypeScript**, mantendo backend Python e scripts PowerShell.

## Stack Tecnológico

| Camada | Tecnologia | Propósito |
|--------|-----------|----------|
| **Frontend** | React 19 + TypeScript + Tailwind CSS | Interface moderna e responsiva |
| **Desktop Framework** | Tauri 2.x | Empacotamento e integração OS |
| **Backend** | FastAPI (Python) | API local para lógica de negócio |
| **Scripts** | PowerShell 7+ | Operações remotas em workstations |
| **Database** | JSON/SQLite (local) | Persistência de dados locais |
| **IPC** | Tauri Commands | Comunicação Frontend ↔ Backend |

## Arquitetura de Camadas

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend (Tauri)                   │
│  - Dashboard, Monitor, Backup, Applications, etc.           │
│  - Componentes TypeScript + Tailwind CSS                    │
└──────────────────────┬──────────────────────────────────────┘
                       │ Tauri Commands (IPC)
┌──────────────────────▼──────────────────────────────────────┐
│              Tauri Runtime (Rust Bridge)                    │
│  - Gerenciamento de processos                              │
│  - Acesso ao sistema de arquivos                           │
│  - Integração com PowerShell                               │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/Stdio
┌──────────────────────▼──────────────────────────────────────┐
│           Backend Python (FastAPI)                          │
│  - Rotas API (/api/dashboard, /api/workstations, etc.)     │
│  - Lógica de negócio                                        │
│  - Integração SQL Server (GTI)                             │
│  - Cache e autenticação                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │ Subprocess
┌──────────────────────▼──────────────────────────────────────┐
│           Scripts PowerShell                                │
│  - consulta.ps1 (WMI queries)                              │
│  - applications.ps1 (lista apps)                           │
│  - backup.ps1 (backup de dados)                            │
│  - install_updates.ps1 (gerenciamento de updates)          │
│  - etc.                                                     │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura de Diretórios

```
wmt-desktop/
├── src-tauri/                    # Configuração Tauri
│   ├── tauri.conf.json          # Config principal
│   ├── src/
│   │   ├── main.rs              # Entry point Rust
│   │   └── lib.rs               # Tauri commands
│   └── Cargo.toml
├── src/                          # Frontend React
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── Monitor.tsx
│   │   ├── Applications.tsx
│   │   ├── Backup.tsx
│   │   ├── AdminUsers.tsx
│   │   └── Login.tsx
│   ├── components/
│   │   ├── Sidebar.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── WorkstationCard.tsx
│   │   └── ...
│   ├── hooks/
│   │   ├── useApi.ts            # Hook para chamar backend
│   │   ├── useAuth.ts
│   │   └── useWorkstations.ts
│   ├── contexts/
│   │   ├── AuthContext.tsx
│   │   └── AppContext.tsx
│   ├── lib/
│   │   ├── api.ts               # Cliente HTTP
│   │   ├── types.ts             # TypeScript types
│   │   └── utils.ts
│   ├── App.tsx
│   └── main.tsx
├── backend/                      # Python FastAPI
│   ├── main.py                  # Entry point
│   ├── app/
│   │   ├── main.py
│   │   ├── routes.py
│   │   ├── config.py
│   │   ├── auth.py
│   │   ├── logger.py
│   │   ├── cache.py
│   │   ├── middleware.py
│   │   ├── printer_snmp.py
│   │   ├── audit.py
│   │   └── metrics.py
│   ├── scripts/                 # PowerShell scripts
│   │   ├── consulta.ps1
│   │   ├── applications.ps1
│   │   ├── backup.ps1
│   │   ├── install_updates.ps1
│   │   ├── pending_updates.ps1
│   │   ├── configmgr_action.ps1
│   │   ├── remote_action.ps1
│   │   └── temporary_share.ps1
│   ├── data/
│   │   ├── users.json
│   │   ├── operation_audit.jsonl
│   │   └── workstations.json
│   ├── requirements.txt
│   └── venv/                    # Virtual environment
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── README.md
```

## Fluxo de Dados

### 1. Inicialização da Aplicação

```
Tauri App Start
  ↓
Tauri Runtime (Rust)
  ├─→ Inicia Backend Python (subprocess)
  ├─→ Aguarda disponibilidade da API (localhost:8000)
  └─→ Carrega Frontend React
  
Frontend React
  ├─→ Verifica autenticação (localStorage/session)
  ├─→ Se não autenticado → Mostra Login
  └─→ Se autenticado → Carrega Dashboard
```

### 2. Requisição de Dados

```
React Component
  ↓ (useEffect)
  ├─→ Chama useApi hook
  │   ↓
  │   ├─→ Faz fetch para http://localhost:8000/api/...
  │   ├─→ Backend FastAPI processa
  │   ├─→ Retorna JSON
  │   └─→ Hook atualiza estado React
  │
  └─→ Component renderiza com dados
```

### 3. Operação Remota (PowerShell)

```
React Component (ex: Backup)
  ↓
Backend FastAPI (/api/backup/start)
  ↓
Python subprocess → PowerShell script
  ├─→ backup.ps1 executa operação remota
  ├─→ Retorna stdout/stderr
  └─→ Python processa resultado
  
Backend retorna status
  ↓
Frontend atualiza UI com resultado
```

## Componentes Principais

### Frontend (React + TypeScript)

**Páginas:**
- `Login.tsx` - Autenticação
- `Dashboard.tsx` - Visão geral da frota
- `Monitor.tsx` - Monitoramento em tempo real
- `Applications.tsx` - Gerenciamento de aplicações
- `Backup.tsx` - Operações de backup
- `AdminUsers.tsx` - Gerenciamento de usuários
- `Account.tsx` - Configurações de conta

**Componentes Reutilizáveis:**
- `Sidebar.tsx` - Navegação lateral
- `StatusBadge.tsx` - Indicadores de status
- `WorkstationCard.tsx` - Card de workstation
- `DataTable.tsx` - Tabela de dados
- `ConfirmDialog.tsx` - Diálogo de confirmação

**Hooks Customizados:**
- `useApi()` - Gerencia requisições HTTP
- `useAuth()` - Gerencia autenticação
- `useWorkstations()` - Gerencia lista de workstations
- `usePolling()` - Polling automático de dados

### Backend (FastAPI + Python)

**Rotas Principais:**
- `POST /api/auth/login` - Autenticação
- `GET /api/dashboard` - Dados do dashboard
- `GET /api/workstations` - Lista de workstations
- `GET /api/workstations/{id}` - Detalhes de workstation
- `POST /api/workstations/{id}/backup` - Iniciar backup
- `GET /api/backup/{job_id}` - Status do backup
- `GET /api/applications/{wk_id}` - Lista de aplicações
- `POST /api/remote-action` - Executar ação remota
- `GET /api/audit-log` - Log de auditoria

**Módulos:**
- `config.py` - Configuração centralizada
- `auth.py` - Autenticação e permissões
- `cache.py` - Cache de resultados
- `logger.py` - Logging estruturado
- `metrics.py` - Coleta de métricas
- `audit.py` - Auditoria de operações
- `printer_snmp.py` - Integração SNMP

### Scripts PowerShell

**Funcionalidades:**
- `consulta.ps1` - WMI queries para dados de workstation
- `applications.ps1` - Enumeração de aplicações instaladas
- `backup.ps1` - Backup de arquivos via SMB
- `install_updates.ps1` - Instalação de updates
- `pending_updates.ps1` - Verificação de updates pendentes
- `configmgr_action.ps1` - Ações SCCM/ConfigMgr
- `remote_action.ps1` - Ações remotas (gpupdate, restart, etc.)
- `temporary_share.ps1` - Criação de compartilhamentos temporários

## Comunicação Entre Camadas

### Frontend → Backend (HTTP)

```typescript
// useApi hook
const { data, loading, error } = useApi('/api/dashboard');

// Internamente:
// fetch('http://localhost:8000/api/dashboard')
```

### Backend → PowerShell (Subprocess)

```python
# routes.py
import subprocess

result = subprocess.run(
    ['powershell', '-NoProfile', '-File', 'scripts/consulta.ps1', '-ComputerName', 'WK001'],
    capture_output=True,
    text=True,
    timeout=30
)
```

### Tauri Commands (opcional para operações específicas)

```typescript
// Frontend
import { invoke } from '@tauri-apps/api/tauri';
const result = await invoke('open_file_dialog');

// Backend (Rust)
#[tauri::command]
fn open_file_dialog() -> String {
    // Implementação
}
```

## Configuração de Ambiente

### Variáveis de Ambiente

```env
# Backend
DEBUG=true
LOG_TO_FILE=true
POWERSHELL_TIMEOUT=30
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=admin123
CACHE_ENABLED=true
CACHE_TTL=300

# GTI SQL Server
GTI_SQL_SERVER=PSQLAPP048-02BR
GTI_SQL_DATABASE=PirelliTools
GTI_SQL_USER=sfloor
GTI_SQL_PASSWORD=perdigao75

# Tauri
TAURI_PRIVATE_KEY=<key>
TAURI_KEY_PASSWORD=<password>
```

## Segurança

1. **Autenticação:** Implementada no FastAPI com JWT/Session
2. **Autorização:** RBAC (Role-Based Access Control)
3. **Comunicação:** HTTP local (localhost:8000) - sem exposição externa
4. **Credenciais:** Armazenadas em arquivo seguro ou variáveis de ambiente
5. **Logs:** Auditoria de todas as operações

## Empacotamento e Distribuição

### Build para Windows

```bash
# Desenvolvimento
npm run tauri dev

# Produção
npm run tauri build

# Resultado
# → src-tauri/target/release/WMT.exe
# → src-tauri/target/release/bundle/msi/WMT_x.x.x_x64_en-US.msi
```

### Build para macOS

```bash
npm run tauri build --target universal-apple-darwin

# Resultado
# → src-tauri/target/universal-apple-darwin/release/WMT.app
# → src-tauri/target/universal-apple-darwin/release/bundle/dmg/WMT_x.x.x_0.app.tar.gz
```

### Build para Linux

```bash
npm run tauri build --target x86_64-unknown-linux-gnu

# Resultado
# → src-tauri/target/x86_64-unknown-linux-gnu/release/WMT
# → src-tauri/target/x86_64-unknown-linux-gnu/release/bundle/deb/wmt_x.x.x_amd64.deb
```

## Próximos Passos

1. ✅ Análise e planejamento
2. → Configurar Tauri com React + TypeScript
3. → Migrar componentes React do frontend
4. → Integrar backend Python
5. → Testar comunicação IPC
6. → Empacotar e distribuir
