# WMT Desktop - Estratégias de Distribuição

## Cenários de Uso

Existem **2 modos principais** de usar o WMT em múltiplos computadores:

### 1️⃣ **Modo Web via IIS (Recomendado para Corporativo)**

#### Cenário
- ✅ Usuários acessam via navegador (Edge, Chrome)
- ✅ Autenticação Windows automática (Kerberos/NTLM)
- ✅ **Zero instalação** no cliente
- ✅ Centralizado em um servidor
- ✅ Fácil manutenção e atualizações

#### Infraestrutura
```
┌─────────────────┐
│ Servidor IIS    │
│ + Backend Python│
└────────┬────────┘
         │ HTTPS + Windows Auth
    ┌────▼──────┐
    │ Navegador │ (qualquer computador)
    │ WMT       │
    └───────────┘
```

#### Vantagens
- ✅ Sem instalação
- ✅ Sem versões fragmentadas
- ✅ Controle centralizado
- ✅ Funciona em qualquer SO com navegador
- ✅ Fácil rollback de versões

#### Desvantagens
- ❌ Requer servidor IIS
- ❌ Sem acesso offline
- ❌ Latência de rede

#### Configuração para Usuários
1. Abrir `https://wmt.empresa.local`
2. Autenticar com Windows (automático)
3. Pronto!

---

### 2️⃣ **Modo Desktop Tauri (Para Usuários Específicos)**

#### Cenário
- ✅ Usuários instalam `.exe` ou `.msi` localmente
- ✅ Backend Python roda como subprocess
- ✅ Funciona offline
- ✅ Interface desktop nativa
- ✅ Integração com SO melhorada

#### Infraestrutura
```
┌──────────────────────────────┐
│ Computador do Usuário        │
│ ┌────────────────────────┐   │
│ │ WMT Desktop (Tauri)    │   │
│ │ ├─ Frontend (React)    │   │
│ │ ├─ Backend (FastAPI)   │   │
│ │ └─ PowerShell Scripts  │   │
│ └────────────────────────┘   │
└──────────────────────────────┘
```

#### Vantagens
- ✅ Funciona offline
- ✅ Performance local
- ✅ Interface desktop
- ✅ Integração melhorada com SO
- ✅ Sem dependência de servidor web

#### Desvantagens
- ❌ Instalação necessária
- ❌ Versões fragmentadas
- ❌ Mais suporte técnico
- ❌ Requer Python/Runtime

#### Configuração para Usuários
1. Baixar `.exe` ou `.msi`
2. Executar instalador
3. Abrir aplicação
4. Pronto!

---

## Recomendação para Seu Caso

### Se você quer **máximo alcance com mínima complexidade**:
👉 **Use IIS (Modo Web)**

Você já tem tudo configurado. Os usuários apenas acessam a URL.

### Se você quer **offline + controle local**:
👉 **Use Desktop Tauri (Modo Desktop)**

Precisa fazer build e distribuir o instalável.

---

## Como Distribuir o Desktop App (Tauri)

### 1. Build o Instalável

```bash
# Compilar para produção (gera .exe / .msi)
pnpm build:tauri

# Resultado:
# Windows: src-tauri/target/release/WMT-Setup.exe (ou .msi)
# macOS: src-tauri/target/release/WMT.app.tar.gz
# Linux: src-tauri/target/release/wmt_*.AppImage
```

### 2. Opções de Distribuição

#### Opção A: Upload Simples
1. Fazer build
2. Salvar `.exe` em compartilhamento de rede
3. Usuários executam: `\\compartilhamento\WMT-Setup.exe`

#### Opção B: Microsoft Intune / Group Policy
```powershell
# Se sua empresa usa AD + Intune
# Distribuir como aplicação gerenciada via GPO
# Usuários recebem automaticamente
```

#### Opção C: Servidor de Download
1. Hospedar `.exe` em servidor HTTPS
2. Enviar link para usuários
3. Usuários baixam e instalam

#### Opção D: Auto-Update
Configure Tauri para atualizar automaticamente:

```json
{
  "updater": {
    "active": true,
    "endpoints": [
      "https://seu-servidor.com/releases/{{target}}/{{current_version}}"
    ],
    "dialog": true,
    "pubkey": "..."
  }
}
```

### 3. Silencioso (MSI para IT)

```powershell
# IT pode fazer instalação silenciosa
msiexec /i WMT-Setup.msi /quiet /norestart
```

---

## Arquitetura Recomendada: HÍBRIDA

### Cenário Ideal

```
┌─────────────────────────────────────────────────────────┐
│                   PRODUÇÃO HÍBRIDA                      │
└─────────────────────────────────────────────────────────┘

┌─ MODO 1: Usuários Web (Navegador) ───────────────────┐
│ • Acesso via IIS: https://wmt.empresa.local          │
│ • Windows Auth automático                            │
│ • Zero instalação                                     │
│ • Melhor para acesso ocasional                        │
└──────────────────────────────────────────────────────┘

┌─ MODO 2: Operadores (Desktop Tauri) ─────────────────┐
│ • Instalação: WMT-Setup.exe                           │
│ • Roda localmente com backend Python                  │
│ • Funciona offline                                    │
│ • Melhor para uso intensivo/diário                    │
└──────────────────────────────────────────────────────┘

         ↓ Ambos podem comunicar com:
      
      • SQL Server (GTI Database)
      • Active Directory (para usuários/grupos)
      • Scripts PowerShell (operações remotas)
```

---

## Configuração por Modo

### MODO WEB (IIS)

#### Para quem acessa:
```
1. Abrir navegador
2. Ir para: https://wmt.empresa.local
3. Autenticar (automático com Windows)
4. Usar aplicação
```

#### Backend corre em:
- Um servidor central (Windows Server)
- Python + FastAPI em `http://127.0.0.1:8000`
- IIS proxy reverso na frente (HTTPS)

#### Configuração de usuário:
**NENHUMA** ✅ (automática com Windows Auth)

---

### MODO DESKTOP (Tauri)

#### Para quem usa:
```
1. Baixar WMT-Setup.exe
2. Executar instalador
3. Abrir aplicação (atalho no desktop)
4. Login (se não usar Windows Auth local)
5. Usar aplicação
```

#### Backend corre em:
- Computador local do usuário
- Python + FastAPI rodando como subprocess
- Frontend React empacotado no Tauri

#### Configuração de usuário:
```
Na primeira execução:
1. Login com credenciais (ou usar Windows Auth local)
2. Selectionar servidor backend (local ou remoto)
3. Preferências de interface
4. Pronto!
```

---

## Tamanho dos Instaláveis

### Desktop Tauri (.exe / .msi)
- **Tamanho**: ~150-250 MB (inclui Rust runtime + Python runtime)
- **Instalado**: ~300-400 MB
- **Tempo instalação**: 2-5 minutos

### Alternativa: Portable (sem instalador)
- Descompactar ZIP
- Executar `.exe` diretamente
- Sem registro no sistema

---

## Manutenção e Atualizações

### Modo Web (IIS)
```
1. Atualizar código no servidor
2. Reiniciar aplicação
3. Todos os usuários veem nova versão automaticamente
✅ Sem nada a fazer no cliente
```

### Modo Desktop (Tauri)
```
OPÇÃO A: Manual
1. Build nova versão
2. Usuários baixam novo .exe
3. Executam instalador novamente

OPÇÃO B: Auto-Update (configurado)
1. Tauri detecta nova versão
2. Download automático
3. Aviso para reiniciar
4. Usuário aprova e reinicia
```

---

## Decisão: Qual Modo Usar?

| Aspecto | Web (IIS) | Desktop (Tauri) |
|---------|-----------|-----------------|
| **Instalação** | ❌ Não (acesso via URL) | ✅ Sim (.exe/.msi) |
| **Configuração** | ❌ Nenhuma | ✅ Mínima |
| **Offline** | ❌ Não | ✅ Sim |
| **Atualizações** | ✅ Automáticas | ❌ Manual ou auto (complexo) |
| **Manutenção** | ✅ Centralizada | ❌ Distribuída |
| **Acessibilidade** | ✅ Qualquer SO + navegador | ❌ Windows (.exe) |
| **Performance** | ⚠️ Latência de rede | ✅ Local |
| **Ideal para** | Acesso ocasional | Uso diário intensivo |

---

## Próximos Passos

### ✅ Se você quer MODO WEB (Recomendado)
1. Servidor IIS com Windows Auth (já configurado! ✅)
2. Backend Python rodando no servidor
3. Usuários acessam via `https://wmt.empresa.local`
4. Nada a instalar no cliente

### ✅ Se você quer MODO DESKTOP
1. Build: `pnpm build:tauri`
2. Distribuir `.exe` via rede/Intune/download
3. Usuários instalam localmente
4. Backend Python roda como subprocess

### ✅ Se você quer AMBOS
1. IIS configurado para web
2. Desktop Tauri para operadores/admins
3. Mesmo backend, duas formas de acesso
4. Máxima flexibilidade

---

## Sua Situação Específica

Você tem:
- ✅ Backend pronto (FastAPI)
- ✅ Frontend pronto (React + Tauri)
- ✅ IIS configurado (acabei de fazer!)
- ✅ Windows Auth pronto

**Recomendação**: **COMECE COM MODO WEB**

Motivos:
1. Zero instalação para usuários finais
2. Fácil manutenção centralizada
3. Já está configurado no IIS
4. Se precisar depois, pode fazer desktop app

Comando para testar agora:
```
1. Iniciar backend: cd backend && python main.py
2. Acessar: https://wmt.empresa.local (ou seu domínio)
3. Pronto!
```
