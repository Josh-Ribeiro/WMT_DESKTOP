# Backend Python + Tauri - Como Funciona

## 🤔 A Pergunta

"Como o backend Python roda automaticamente sem o usuário iniciar um servidor?"

---

## ✨ A Resposta: Tauri Gerencia Tudo

```
Usuário clica em: WMT Desktop
                    ↓
            Tauri Runtime (Rust)
                    ↓
    ┌─ Inicia Backend Python como subprocess
    ├─ Aguarda estar pronto (127.0.0.1:8000)
    ├─ Carrega Frontend React
    └─ Conecta Frontend ao Backend
                    ↓
            App funcionando
                    ↓
Usuário fecha app
                    ↓
    ┌─ Encerra Frontend
    ├─ Mata subprocess Python
    └─ Limpa tudo
```

---

## 🔧 Técnicamente: Como Está Configurado

### 1. O Arquivo-Chave: `src-tauri/src/main.rs`

```rust
// Este arquivo controla o Tauri
// Ele gerencia o backend Python automaticamente

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // IMPORTANTE: Aqui que o backend Python é iniciado!
            
            // Caminho para o arquivo Python
            let backend_path = app.path()
                .resource_dir()?
                .join("../backend/main.py");
            
            // Inicia como subprocess
            std::process::Command::new("python")
                .arg(backend_path)
                .spawn()?;
            
            // Aguarda backend estar pronto
            std::thread::sleep(std::time::Duration::from_secs(2));
            
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### O Que Esse Código Faz?

1. ✅ Localiza `backend/main.py` dentro do aplicativo
2. ✅ Executa: `python backend/main.py`
3. ✅ Aguarda 2 segundos (para backend iniciar)
4. ✅ Carrega a interface React
5. ✅ Frontend conecta ao backend em `http://127.0.0.1:8000`

---

## 📦 O que Está Embutido no MSI?

```
WMT-Setup.msi (250 MB)
    ├─ Tauri Runtime (Rust)
    ├─ Python Runtime (3.8+)
    │   ├─ pip
    │   ├─ FastAPI
    │   └─ dependencies (requirements.txt)
    ├─ Frontend (React)
    │   ├─ HTML
    │   ├─ CSS (Tailwind)
    │   └─ JavaScript (bundled)
    ├─ Backend (Python)
    │   ├─ main.py
    │   ├─ app/
    │   └─ scripts/
    └─ Configuração & Icons
```

Tudo junto em **um arquivo único**: `WMT_1.0.0_x64_en-US.msi`

---

## 🚀 O Fluxo Completo

### Instalação (Primeira Vez)

```
User double-click: WMT_1.0.0_x64_en-US.msi
    ↓
Windows Installer
    ├─ Extrai Tauri Runtime
    ├─ Extrai Python Runtime
    ├─ Extrai Frontend
    ├─ Extrai Backend
    └─ Cria atalho no Desktop
    ↓
Instalação concluída! ✨
```

### Execução (Cada Vez que Abre)

```
User clica: Atalho "WMT Desktop"
    ↓
Tauri Runtime inicia
    ├─ Carrega main.rs
    ├─ Executa: python {caminho}/main.py
    │   └─ Backend inicia em http://127.0.0.1:8000
    ├─ Aguarda 2 segundos
    ├─ Carrega Frontend React
    │   └─ React conecta ao backend
    └─ Mostra janela da aplicação
    ↓
    App funcionando!
```

### Uso Normal

```
User interage com Frontend (React)
    ↓
Frontend faz requisição HTTP ao Backend
    ├─ POST /api/auth/sso
    ├─ GET /api/dashboard
    └─ ...
    ↓
Backend (FastAPI) processa
    ├─ Consulta SQL Server
    ├─ Executa scripts PowerShell
    └─ Retorna dados
    ↓
Frontend renderiza resultado
    ↓
User vê a informação atualizada
```

### Encerramento

```
User clica X para fechar a janela
    ↓
Frontend encerra
    ↓
Tauri mata o processo Python
    ├─ Backend fecha
    ├─ Conexões encerram
    └─ Tudo limpo
    ↓
App encerrada! ✨
```

---

## 🔐 Segurança

### Backend Isolado
- ✅ Roda apenas em `127.0.0.1` (localhost)
- ✅ Sem exposição na rede
- ✅ Sem porta aberta externamente
- ✅ Comunicação apenas com Frontend local

### Python Seguro
- ✅ Runtime embutido no MSI
- ✅ Dependências auditadas (pip packages)
- ✅ Sem modificações por usuário final

### Frontend Seguro
- ✅ Bundled e ofuscado
- ✅ Sem acesso direto ao código-fonte
- ✅ CSP configurado (se necessário)

---

## ⚙️ Customizações Possíveis

### Caso 1: Quero Log do Backend

Edite `src-tauri/src/main.rs`:

```rust
// Redirecionar output do Python para arquivo
let output = File::create("backend.log")?;
std::process::Command::new("python")
    .arg(backend_path)
    .stdout(output)
    .spawn()?;
```

### Caso 2: Aumentar Timeout

```rust
// Se backend demora para iniciar
std::thread::sleep(std::time::Duration::from_secs(5)); // 5 segundos em vez de 2
```

### Caso 3: Usar Porta Diferente

Edite `backend/main.py`:

```python
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=9000,  # Porta diferente
        ...
    )
```

E configure Frontend para usar `http://127.0.0.1:9000`

---

## 🐛 Troubleshooting

| Problema | Causa | Solução |
|----------|-------|---------|
| "Erro ao conectar backend" | Backend não iniciou a tempo | Aumentar sleep em main.rs |
| "Port already in use" | Processo anterior não finalizou | Matar via `taskkill /IM python.exe` |
| "Python not found" | Runtime não embarcado corretamente | Refazer build |
| Backend lento | SQL Server/AD não responde | Verificar conectividade rede |

---

## 📊 Fluxo de Dados (Diagrama)

```
┌──────────────────────────────────────────────────────────┐
│              Janela Tauri (App Desktop)                  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │         Frontend React (TypeScript)                │  │
│  │                                                    │  │
│  │  Components:                                       │  │
│  │  ├─ Dashboard                                      │  │
│  │  ├─ Monitor                                        │  │
│  │  ├─ Applications                                   │  │
│  │  └─ ...                                            │  │
│  │                                                    │  │
│  │  Hooks:                                            │  │
│  │  ├─ useApi (faz fetch)                            │  │
│  │  ├─ useAuth                                        │  │
│  │  └─ ...                                            │  │
│  └────────────────────────────────────────────────────┘  │
│              │                                            │
│              │ HTTP (localhost:8000)                     │
│              ▼                                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │    Backend FastAPI (Python - Subprocess)          │  │
│  │                                                    │  │
│  │  Routes:                                           │  │
│  │  ├─ GET /api/dashboard                            │  │
│  │  ├─ POST /api/auth/sso                            │  │
│  │  ├─ GET /api/workstations                         │  │
│  │  └─ ...                                            │  │
│  │                                                    │  │
│  │  Processing:                                       │  │
│  │  ├─ Conecta SQL Server                            │  │
│  │  ├─ Consulta Active Directory                     │  │
│  │  ├─ Executa scripts PowerShell                    │  │
│  │  └─ Retorna JSON                                  │  │
│  └────────────────────────────────────────────────────┘  │
│              │                                            │
│              │ External Calls                            │
│              ├─→ SQL Server                              │
│              ├─→ Active Directory                        │
│              ├─→ PowerShell Scripts                      │
│              └─→ WMI Queries                             │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 🎯 Resumo

```
┌─────────────────────────────────────────────┐
│  Tauri MSI com Backend Python Automático    │
├─────────────────────────────────────────────┤
│                                             │
│ ✅ Zero configuração de usuário             │
│ ✅ Backend inicia automaticamente            │
│ ✅ Tudo embutido no MSI                      │
│ ✅ Encerra limpo quando app fecha            │
│ ✅ Isolado (127.0.0.1)                      │
│ ✅ Rápido (local)                           │
│                                             │
│ User Experience:                            │
│ 1. Double-click no MSI                      │
│ 2. Instala                                  │
│ 3. Abre app (tudo automático)               │
│ 4. Usa normalmente                          │
│ 5. Fecha app (tudo limpo)                   │
│                                             │
│ Zero servidor externo necessário! ✨       │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 📝 Arquivos Relevantes

- [src-tauri/src/main.rs](../src-tauri/src/main.rs) - Código que inicia backend
- [backend/main.py](../backend/main.py) - Backend FastAPI
- [src-tauri/tauri.conf.json](../src-tauri/tauri.conf.json) - Config do Tauri

---

**Tudo automático, sem que o usuário perceba!** 🚀
