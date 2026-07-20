# 🚀 Build MSI - Guia Prático (Passo a Passo)

## O Que Você Está Fazendo

```
Seu código → [pnpm build:tauri] → WMT-Setup.msi (~250 MB)
                                       ↓
                                  Usuários instalam
                                       ↓
                                Backend + Frontend
                                   roda local
```

---

## ✅ Pré-requisitos (1x apenas)

Execute isso **uma única vez** para preparar seu computador:

### 1. Instalar Rust

```powershell
# Download em: https://rustup.rs/
# Ou execute:
irm https://sh.rustup.rs -outfile rustup-init.exe
.\rustup-init.exe
# Selecione: 1 (instalação padrão)
# Depois:
rustup --version
```

### 2. Instalar Visual Studio Build Tools

```
https://visualstudio.microsoft.com/downloads/
→ "Community Edition" → Instalar
→ Na tela de workloads, selecione: "Desktop development with C++"
→ Instalar (~5 GB)
```

### 3. Verificar Node.js e Python

```powershell
node --version      # Deve ser 18+
python --version    # Deve ser 3.8+
pnpm --version      # Deve estar instalado
```

---

## 🔨 Compilar o MSI (Passo a Passo)

### Passo 1: Abrir Terminal PowerShell

```powershell
cd c:\Users\et1ribeijo\Desktop\wmt-desktop
```

### Passo 2: Build do Frontend

```powershell
pnpm install
pnpm build
```

**Tempo:** 2-3 minutos
**O que faz:** Compila React, TypeScript, Tailwind para HTML/CSS/JS

### Passo 3: Build do Tauri (Frontend + Backend + Rust)

```powershell
pnpm build:tauri
```

**Tempo:** 
- Primeira vez: 30-45 minutos (compila Rust inteiro)
- Builds seguintes: 5-10 minutos

**O que faz:**
- ✅ Compila código Rust
- ✅ Empacota Frontend React
- ✅ Embute Backend Python
- ✅ Gera MSI + EXE + Portable

### Resultado: Encontre seus Arquivos

```
src-tauri/target/release/

├─ WMT_1.0.0_x64_en-US.msi          ← MSI (instalável) 🎁
├─ WMT_1.0.0_x64_en-US.msi.sig      ← Assinatura
├─ WMT.exe                          ← Executável portable
└─ ...
```

---

## 💾 Copiar para Distribuição

### Copiar MSI para Compartilhamento de Rede

```powershell
# Criar pasta de releases
mkdir \\sua-rede\compartilhamento\wmt-releases

# Copiar arquivos
Copy-Item "src-tauri\target\release\WMT_1.0.0_x64_en-US.msi" `
  -Destination "\\sua-rede\compartilhamento\wmt-releases\"

Copy-Item "src-tauri\target\release\WMT_1.0.0_x64_en-US.msi.sig" `
  -Destination "\\sua-rede\compartilhamento\wmt-releases\"

Write-Host "✓ Copiad para: \\sua-rede\compartilhamento\wmt-releases\"
```

### Compartilhar Link com Usuários

```
Pessoal,

Podem instalar WMT Desktop em:

\\sua-rede\compartilhamento\wmt-releases\WMT_1.0.0_x64_en-US.msi

Steps:
1. Abrir arquivo
2. Executar installer (próximo, próximo, finalizar)
3. Pronto!

Qualquer dúvida, chamem!
```

---

## 🧪 Testar o MSI Antes de Distribuir

### Testar Instalação Local

```powershell
# Ir para pasta de release
cd "src-tauri\target\release\"

# Executar MSI
.\WMT_1.0.0_x64_en-US.msi

# Steps:
# 1. Next
# 2. Accept
# 3. Install
# 4. Finish
```

### Verificar se Funcionou

1. Procure "WMT Desktop" no Menu Iniciar
2. Clique para abrir
3. Verifique:
   - ✅ Frontend carrega (página React)
   - ✅ Backend responde
   - ✅ Sem erros

### Desinstalar para Testar de Novo

```powershell
# Control Panel → Programs → Programs and Features
# Procure "WMT Desktop"
# Clique em "Uninstall"
```

---

## 🔄 Atualizar para Nova Versão

### 1. Fazer Mudanças no Código

```powershell
# Editar código, testes, etc
git add .
git commit -m "Fix bug tal"
```

### 2. Bumpar Versão

```powershell
# Versão atual: 1.0.0 → Nova: 1.0.1
.\scripts\bump-version.ps1 -NewVersion "1.0.1"

# Ou auto-increment (patch):
.\scripts\bump-version.ps1 -Type "patch"  # 1.0.0 → 1.0.1
```

### 3. Build da Nova Versão

```powershell
pnpm build:tauri
```

Resultado:
```
WMT_1.0.1_x64_en-US.msi
WMT_1.0.1_x64_en-US.msi.sig
```

### 4. Distribuir para Usuários

```powershell
# Copiar nova versão
Copy-Item "src-tauri\target\release\WMT_1.0.1_x64_en-US.msi" `
  -Destination "\\sua-rede\compartilhamento\wmt-releases\"

# Notificar usuários:
# "Nova versão 1.0.1 disponível!"
```

### 5. Usuários Atualizam

Quando a nova versão está disponível:
- Usuário baixa novo MSI
- Instala (vai atualizar a versão anterior)
- Pronto! ✨

---

## 🔧 Troubleshooting

### Build Falha em Rust

```powershell
# Limpar tudo
cargo clean

# Reinstalar
pnpm install

# Build de novo
pnpm build:tauri
```

### Erro: "Python not found"

Verifique que o caminho do Python está correto em `src-tauri/src/main.rs`

### MSI Muito Grande (> 500 MB)

Remova arquivos desnecessários:
```powershell
# Deletar cache/node_modules antes de build
rm -r backend/__pycache__
rm -r node_modules
pnpm install --frozen-lockfile
pnpm build:tauri
```

### Instalação Lenta

- MSI precisa ser extraído (~250 MB)
- Tempo normal: 2-5 minutos
- Disco SSD: mais rápido

---

## 📊 Resumo: De Código a Usuário

```
┌─────────────────────────────────────┐
│ Você                                │
│ ├─ Edita código                     │
│ └─ Roda: pnpm build:tauri           │
└────────────┬────────────────────────┘
             ↓
        MSI Gerado (~250 MB)
             ↓
┌────────────────────────────────────────┐
│ Você Copia para Compartilhamento      │
│ \\rede\compartilhamento\releases\      │
└────────────┬────────────────────────────┘
             ↓
┌────────────────────────────────────────┐
│ Usuário                               │
│ ├─ Baixa MSI                          │
│ ├─ Double-click                       │
│ ├─ Instala (2-5 min)                  │
│ └─ App pronto!                        │
└────────────────────────────────────────┘
             ↓
    Backend + Frontend rodando local
    Sem config manual! ✨
```

---

## 🎯 Commands Rápidos

```powershell
# Setup (1x)
pnpm install
rustup --version

# Build
pnpm build:tauri

# Bumpar versão
.\scripts\bump-version.ps1 -Type "patch"

# Copiar para release
Copy-Item "src-tauri\target\release\WMT_*.msi" `
  -Destination "\\rede\releases\"

# Testar MSI
.\src-tauri\target\release\WMT_1.0.0_x64_en-US.msi
```

---

## ❓ FAQs

**P: Quanto tempo leva o build?**
R: Primeira vez 45 min. Depois 5-10 min.

**P: Posso fazer build em Mac/Linux?**
R: Sim, mas precisa da toolchain do Rust para cada SO.

**P: O tamanho está certo (250 MB)?**
R: Sim, inclui Rust runtime + Python runtime + Frontend.

**P: Como fazer update automático?**
R: Configure `updater` em `tauri.conf.json` (veja TAURI_BUILD_GUIDE.md).

**P: Posso distribuir via USB?**
R: Sim, copie o MSI para USB e distribua.

---

## 🚀 Você Está Pronto!

```bash
pnpm build:tauri
```

Pronto para iniciar seu primeiro build! 🎉
