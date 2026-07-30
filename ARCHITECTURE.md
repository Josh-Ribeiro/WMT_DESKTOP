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
| **Database** | SQLite (local) | Estado transacional e migração do JSON legado |
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
│   │   ├── main.py              # App factory e registro dos routers
│   │   ├── schemas.py           # Modelos de entrada e saída
│   │   ├── runtime.py           # Fachada de compatibilidade
│   │   ├── core/
│   │   │   ├── config.py        # Ambiente e constantes
│   │   │   ├── security.py      # Hash, papéis e utilitários SSO
│   │   │   ├── validators.py    # Validação compartilhada
│   │   │   └── utils.py         # Utilitários de plataforma
│   │   ├── repositories/
│   │   │   └── state.py         # Persistência JSON atual
│   │   ├── services/
│   │   │   ├── auth.py
│   │   │   ├── backup.py
│   │   │   ├── diagnostics.py
│   │   │   ├── directory.py
│   │   │   ├── documents.py
│   │   │   ├── inventory.py
│   │   │   ├── powershell.py
│   │   │   ├── remote_jobs.py
│   │   │   └── ...
│   │   └── api/                 # Camada HTTP por domínio
│   │       ├── auth.py
│   │       ├── backup.py
│   │       ├── dashboard.py
│   │       ├── diagnostics.py
│   │       ├── directory.py
│   │       ├── documents.py
│   │       ├── remote_operations.py
│   │       ├── settings.py
│   │       ├── software_center.py
│   │       ├── system.py
│   │       ├── update_jobs.py
│   │       └── users.py
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
│   │   ├── state.db              # Estado transacional
│   │   ├── state.json            # Legado, somente para migração
│   │   └── updates/              # Manifestos e artefatos
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
  ├─→ Modo central: usa a API HTTPS configurada
  ├─→ Modo sidecar: inicia wmt-backend.exe em loopback
  ├─→ Valida /health/ready e api_version
  └─→ Carrega Frontend React
  
Frontend React
  ├─→ Restaura sessão por cookie HttpOnly
  ├─→ Se não autenticado → Mostra Login
  └─→ Aplica política central de rota e permissão
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
# Bootstrap local opcional
WMT_BOOTSTRAP_ADMIN_USERNAME=admin
WMT_BOOTSTRAP_ADMIN_PASSWORD=<senha-exclusiva-com-12-ou-mais-caracteres>
WMT_BOOTSTRAP_ADMIN_EMAIL=wmt-admin@empresa.local

# Persistência
WMT_STATE_DB_PATH=C:\ProgramData\WMT\state.db

# SSO via proxy local/IIS
WMT_SSO_ENABLED=true
WMT_SSO_TRUSTED_PROXY_IPS=127.0.0.1,::1
WMT_SSO_ALLOWED_GROUPS=<grupo-autorizado>
WMT_SSO_ADMIN_GROUPS=<grupo-administrador>

# Tauri
TAURI_PRIVATE_KEY=<key>
TAURI_KEY_PASSWORD=<password>
```

## Segurança

1. **Autenticação:** Sessões opacas gerenciadas pelo FastAPI
2. **Autorização:** RBAC (Role-Based Access Control)
3. **Sessão:** Cookie `HttpOnly` e CSRF em memória; bearer desativado por padrão
4. **Comunicação:** HTTPS em produção; HTTP somente para loopback em desenvolvimento
5. **Credenciais:** Não há senha padrão; bootstrap exige segredo externo
6. **Cliente:** CSP ativa e atualizador restrito a HTTPS assinado
7. **Logs:** Auditoria de todas as operações

## Runtime do Backend

Builds corporativos usam o modo `central` e não iniciam um backend local.
Edições locais podem usar `sidecar`, empacotado como executável independente de
Python. O Tauri valida `service` e `api_version`, mantém logs persistentes e
encerra somente o processo que iniciou.

Consulte [Runtime do backend](docs/backend-runtime.md).

## Autorização no React

`AuthProvider`, `AuthenticationGuard`, `PermissionGuard` e
`AuthenticatedLayout` formam a camada central de sessão e navegação. Menu e
roteador usam a mesma política declarada em `client/src/lib/routePolicy.ts`.
O FastAPI permanece como autoridade final.

Consulte [Autorização no frontend](docs/frontend-authorization.md).

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
