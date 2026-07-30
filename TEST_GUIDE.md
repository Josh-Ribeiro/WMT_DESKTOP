# WMT Desktop - Guia de Testes

## Verificação de Estrutura

### 1. Verificar arquivos do frontend

```bash
# Verificar se os arquivos React existem
ls -la client/src/pages/
ls -la client/src/components/
ls -la client/src/hooks/
```

Esperado:
- ✅ `pages/Login.tsx`
- ✅ `pages/Dashboard.tsx`
- ✅ `pages/Monitor.tsx`
- ✅ `components/Sidebar.tsx`
- ✅ `components/StatusBadge.tsx`
- ✅ `hooks/useApi.ts`
- ✅ `hooks/useAuth.ts`

### 2. Verificar arquivos do backend

```bash
# Verificar se os arquivos Python existem
ls -la backend/app/
ls -la backend/scripts/
ls -la backend/data/
```

Esperado:
- ✅ `app/main.py`
- ✅ `app/config.py`
- ✅ `app/auth.py`
- ✅ `app/powershell.py`
- ✅ `app/logger.py`
- ✅ `app/audit.py`
- ✅ `scripts/*.ps1` (PowerShell scripts)
- ✅ `data/workstations.json`
- ✅ `data/users.json`

### 3. Verificar arquivos Tauri

```bash
# Verificar se os arquivos Tauri existem
ls -la src-tauri/
ls -la src-tauri/src/
```

Esperado:
- ✅ `Cargo.toml`
- ✅ `tauri.conf.json`
- ✅ `src/main.rs`
- ✅ `src/commands.rs`
- ✅ `src/lib.rs`

## Testes de Desenvolvimento

### 1. Testar Backend FastAPI

```bash
# Terminal 1: Ativar virtual environment e iniciar backend
cd backend
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate no Windows
pip install -r requirements-dev.txt
python main.py

# Esperado:
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 2. Testar Frontend (sem Tauri)

```bash
# Terminal 2: Iniciar servidor Vite
pnpm install
pnpm dev

# Esperado:
# ➜  Local:   http://localhost:5173/
```

### 3. Testar endpoints da API

```bash
# Terminal 3: Testar endpoints
curl http://localhost:8000/health
# Esperado: {"status":"ok"}

curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<senha-configurada-no-bootstrap>"}'
# Esperado: {"access_token":"...","token_type":"bearer","user":"admin",...}

curl http://localhost:8000/api/dashboard
# Esperado: {"total_workstations":2,"online":1,"offline":1,...}

curl http://localhost:8000/api/workstations
# Esperado: {"workstations":[...],"total":2}
```

### 4. Testar Frontend no navegador

- Abrir http://localhost:5173
- Fazer login com o usuário provisionado por bootstrap ou SSO
- Verificar se o Dashboard carrega
- Clicar em "Monitor" para ver lista de workstations
- Clicar em "Refresh" para testar refetch

## Checklist de Funcionalidades

### Autenticação
- [ ] Login com credenciais válidas
- [ ] Erro ao fazer login com credenciais inválidas
- [ ] Logout funciona
- [ ] Sessão restaurada por cookie sem token no localStorage
- [ ] Operações de escrita rejeitam requisições sem CSRF

### Dashboard
- [ ] Carrega dados do backend
- [ ] Mostra KPIs (Total, Online, Offline, etc.)
- [ ] Botão Refresh funciona
- [ ] Mostra atividades recentes

### Monitor
- [ ] Lista workstations
- [ ] Mostra status com badges coloridas
- [ ] Atualiza automaticamente a cada 30 segundos
- [ ] Botão Refresh funciona

### Sidebar
- [ ] Navegação entre páginas funciona
- [ ] Links ativos são destacados
- [ ] Botão Logout funciona
- [ ] Pode ser colapsado

### Componentes
- [ ] StatusBadge mostra cores corretas para cada status
- [ ] Buttons têm estados hover/active
- [ ] Cards têm sombras e bordas corretas
- [ ] Inputs aceitam entrada de texto

## Testes de Build

### Build do Frontend

```bash
pnpm build
# Esperado: dist/ criado com arquivos otimizados
```

### Build do Tauri (requer Rust)

```bash
# Instalar Rust (se não tiver)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build para desenvolvimento
pnpm dev:tauri
# Esperado: Aplicação Tauri abre

# Build para produção
pnpm build:tauri
# Esperado: Executável criado em src-tauri/target/release/
```

## Troubleshooting

### Erro: "Backend is not responding"

```bash
# Verificar se backend está rodando
curl http://localhost:8000/api/health

# Se não funcionar:
cd backend
source venv/bin/activate
python main.py
```

### Erro: "Module not found"

```bash
# Reinstalar dependências
cd backend
pip install -r requirements-dev.txt

# Frontend
pnpm install
```

### Erro: "Port 8000 already in use"

```bash
# Encontrar e matar processo
lsof -i :8000
kill -9 <PID>

# Ou usar porta diferente (editar backend/app/main.py)
```

### Erro: "CORS error"

- Verificar se backend está em `http://127.0.0.1:8000`
- Verificar se frontend está em `http://localhost:5173` ou `http://localhost:3000`
- Verificar CORS middleware em `backend/app/main.py`

## Performance

### Métricas esperadas

- **Frontend load time**: < 2s
- **API response time**: < 500ms
- **Dashboard refresh**: < 1s
- **Monitor auto-refresh**: 30s interval

### Otimizações implementadas

- React 19 com lazy loading
- FastAPI com caching
- Tauri com empacotamento eficiente
- Polling configurável

## Próximos Passos

1. ✅ Estrutura base completa
2. → Testar endpoints da API
3. → Testar frontend no navegador
4. → Compilar Tauri para desktop
5. → Distribuir executável

## Suporte

Para problemas, verificar:
1. Saída do backend FastAPI/serviço
2. Console do navegador (F12)
3. Estado transacional em `backend/data/state.db`
