# WMT Desktop - Guia de Build, Auto-Update e Distribuição

## 🎯 Arquitetura do Tauri MSI

```
WMT-Setup.msi (~250 MB)
    ↓
    ├─ Frontend (React) - embutido
    ├─ Backend (Python) - embutido
    ├─ Runtime (Rust/Webview2) - embutido
    └─ Configuração Updater - integrada

User double-click
    ↓
Instala em: C:\Users\{user}\AppData\Local\Programs\WMT Desktop\
    ↓
Cria shortcut no Desktop
    ↓
Backend inicia automaticamente
    ↓
Frontend carrega
    ↓
Pronto! Sem config manual
```

---

## 📦 Build do Instalável

### Pré-requisitos
```powershell
# 1. Node.js 18+
node --version

# 2. Rust
rustc --version

# 3. Python 3.8+ (já tem)
python --version

# 4. pnpm
pnpm --version

# 5. Visual Studio Build Tools (para compilar Rust)
# Instale em: https://visualstudio.microsoft.com/downloads/
# Selecione "Desktop development with C++"
```

### Fazer o Build (MSI + EXE)

```bash
# No diretório raiz do projeto

# 1. Instalar dependências
pnpm install

# 2. Compilar Frontend
pnpm build

# 3. Compilar + Empacotar (Tauri)
pnpm build:tauri

# Resultado:
# - Windows MSI: src-tauri/target/release/WMT_1.0.0_x64_en-US.msi
# - Windows Portable: src-tauri/target/release/WMT.exe
# - Signature: src-tauri/target/release/WMT_1.0.0_x64_en-US.msi.sig
```

### Tempo de Build
- **Primeira vez**: 30-45 minutos (compila Rust)
- **Builds subsequentes**: 5-10 minutos
- **Tamanho final**: ~250-300 MB

---

## 🔄 Versionamento e Auto-Update

### 1. Bumpar Versão

```bash
# Editar dois arquivos:
# 1. src-tauri/tauri.conf.json
# 2. package.json

# De:
"version": "1.0.0"

# Para:
"version": "1.0.1"

# Ou use script (crie este arquivo):
```

Crie [bump-version.ps1](../scripts/bump-version.ps1):

```powershell
param([string]$NewVersion = "1.0.1")

$tauriConfPath = ".\src-tauri\tauri.conf.json"
$packagePath = ".\package.json"

# Atualizar tauri.conf.json
$tauriConf = Get-Content $tauriConfPath | ConvertFrom-Json
$tauriConf.version = $NewVersion
$tauriConf | ConvertTo-Json | Out-File $tauriConfPath

# Atualizar package.json
$package = Get-Content $packagePath | ConvertFrom-Json
$package.version = $NewVersion
$package | ConvertTo-Json | Out-File $packagePath

Write-Host "✓ Versão bumped para $NewVersion"
```

### 2. Gerar Build + Signature

```bash
# 1. Bumpar versão
.\scripts\bump-version.ps1 -NewVersion "1.0.1"

# 2. Build
pnpm build:tauri

# 3. Resultado:
# src-tauri/target/release/WMT_1.0.1_x64_en-US.msi
# src-tauri/target/release/WMT_1.0.1_x64_en-US.msi.sig
```

---

## 🚀 Configurar Auto-Update

### Opção A: GitHub Releases (Gratuito)

1. **Criar repositório GitHub**
```
https://github.com/sua-empresa/wmt-desktop
```

2. **Editar tauri.conf.json**
```json
{
  "updater": {
    "active": true,
    "endpoints": [
      "https://github.com/sua-empresa/wmt-desktop/releases/download/v{{current_version}}/update.json"
    ],
    "dialog": true,
    "pubkey": "..."
  }
}
```

3. **Gerar chave publica** (para assinar releases)
```bash
# Instalar ferramenta
cargo install tauri-cli

# Gerar keys
tauri signer generate -w ~/.tauri/key.txt
```

4. **Fazer release no GitHub**
```bash
# Git push
git tag v1.0.1
git push origin v1.0.1

# Upload dos arquivos:
# - WMT_1.0.1_x64_en-US.msi
# - WMT_1.0.1_x64_en-US.msi.sig
```

### Opção B: Servidor Próprio

1. **Editar tauri.conf.json**
```json
{
  "updater": {
    "active": true,
    "endpoints": [
      "https://seu-servidor.com/api/update/{{target}}/{{current_version}}"
    ],
    "dialog": true,
    "pubkey": "..."
  }
}
```

2. **Servidor retorna JSON**
```json
{
  "version": "1.0.1",
  "notes": "Corrigidos bugs de autenticação",
  "pub_date": "2026-06-02T10:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "signature": "conteúdo do .sig",
      "url": "https://seu-servidor.com/releases/WMT_1.0.1_x64_en-US.msi"
    }
  }
}
```

---

## 📊 Fluxo de Update para o Usuário

```
Usuário abre app
    ↓
Tauri checa: "Há nova versão?"
    ↓
Conecta em seu endpoint
    ↓
Compara versão local vs servidor
    ↓
Se houver atualização:
    - Dialog: "Versão 1.0.1 disponível"
    - Botão: "Atualizar agora" / "Depois"
    ↓ (se clicou "Agora")
Download no background
    ↓
Verifica assinatura
    ↓
Instala MSI automaticamente
    ↓
Reinicia app
    ↓
Novo update aplicado! ✨
```

---

## 🎁 Distribuição para Usuários

### Opção 1: Compartilhamento de Rede

```powershell
# Copiar para servidor
Copy-Item "src-tauri/target/release/WMT_1.0.1_x64_en-US.msi" `
  -Destination "\\srv-central\compartilhamento\WMT\"

# Usuários acessam:
# \\srv-central\compartilhamento\WMT\WMT_1.0.1_x64_en-US.msi
```

### Opção 2: Intune / Group Policy

```powershell
# Upload para Intune
# Microsoft Intune → Apps → Windows apps → Linha de negócios
# Selecionar: WMT_1.0.1_x64_en-US.msi
# Atribuir aos grupos de usuários desejados

# Resultado: Usuários recebem app automaticamente
```

### Opção 3: GitHub Releases (Público)

```
https://github.com/sua-empresa/wmt-desktop/releases/tag/v1.0.1
Usuários baixam: WMT_1.0.1_x64_en-US.msi
```

### Opção 4: Portal Corporativo

Hospedar em página com botão de download:
```html
<a href="https://seu-portal.com/wmt/latest">
  Baixar WMT Desktop (v1.0.1)
</a>
```

---

## 🔧 Gerenciar Backend Python Automaticamente

### Como Funciona?

O Tauri (`main.rs`) gerencia o backend Python:

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // Iniciar backend Python como subprocess
            let backend_path = app.path().resource_dir()?
                .join("../backend/main.py");
            
            std::process::Command::new("python")
                .arg(backend_path)
                .spawn()?;
            
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### O que Isso Significa?

- ✅ Backend inicia **automaticamente** quando app abre
- ✅ Backend encerra quando app fecha
- ✅ Usuário **não vê terminal Python**
- ✅ Sem necessidade de configuração

---

## 📝 Guia Rápido: Fazer Release

```bash
# 1. Fazer mudanças no código
git add .
git commit -m "Add nova feature"

# 2. Bumpar versão
.\scripts\bump-version.ps1 -NewVersion "1.0.1"

# 3. Build
pnpm build:tauri

# 4. Git tag e push
git tag v1.0.1
git push origin v1.0.1

# 5. Upload no GitHub Releases (ou seu servidor)
# - WMT_1.0.1_x64_en-US.msi
# - WMT_1.0.1_x64_en-US.msi.sig
# - Release notes

# 6. Pronto!
# Usuários veem notificação de update na app
```

---

## 🔒 Assinatura de Releases

### Gerar Chave (1x)

```bash
cargo install tauri-cli
tauri signer generate -w ~/.tauri/key.txt

# Copiar a chave pública para tauri.conf.json
```

### Assinar Release (a cada build)

```bash
tauri signer sign "./src-tauri/target/release/WMT_1.0.1_x64_en-US.msi" \
  --key ~/.tauri/key.txt
```

---

## ⚙️ Configuração Recomendada

### tauri.conf.json (Produção)

```json
{
  "productName": "WMT Desktop",
  "version": "1.0.0",
  "identifier": "com.wmt.desktop",
  "build": {
    "beforeBuildCommand": "pnpm build",
    "frontendDist": "../dist"
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "nsis"]
  },
  "updater": {
    "active": true,
    "endpoints": [
      "https://seu-dominio.com/releases/{{target}}/{{current_version}}"
    ],
    "dialog": true,
    "pubkey": "sua-chave-publica"
  }
}
```

---

## 📋 Checklist: Release para Produção

- [ ] Código testado e pronto
- [ ] Versão bumped (tauri.conf.json + package.json)
- [ ] Build bem-sucedido: `pnpm build:tauri`
- [ ] MSI testado (instalação, funcionamento)
- [ ] Release notes escritas
- [ ] Arquivo `.sig` gerado
- [ ] Pushed para GitHub/servidor
- [ ] Update endpoint funciona
- [ ] Usuários notificados
- [ ] Monitorar feedback

---

## 🆘 Troubleshooting

| Problema | Solução |
|----------|---------|
| Build falha em Rust | `cargo clean` + reinstalar Rust |
| Python não inicia | Verificar caminho do `main.py` em `lib.rs` |
| Auto-update não funciona | Verificar `endpoints` em `tauri.conf.json` |
| Assinatura inválida | Regenerar com `tauri signer generate` |
| MSI muito grande | Remover arquivos desnecessários do `backend/` |

---

## 📊 Resumo

```
┌─────────────────────────────────────────────┐
│  TAURI MSI - INSTALÁVEL + AUTO-UPDATE       │
├─────────────────────────────────────────────┤
│                                             │
│ Usuário:                                    │
│ 1. Baixa WMT_1.0.0_x64_en-US.msi           │
│ 2. Double-click → Instala                  │
│ 3. Abre app                                 │
│ 4. Pronto! ✨                               │
│                                             │
│ Backend Python:                             │
│ - Inicia automaticamente                   │
│ - Roda como subprocess                     │
│ - Encerra com app                          │
│ - Sem configuração                         │
│                                             │
│ Atualizações:                               │
│ - Verifica auto ao abrir                   │
│ - Dialog amigável                          │
│ - Download + instalação automática         │
│ - Reinicia app                             │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 🚀 Próximos Passos

1. ✅ Testar build local: `pnpm build:tauri`
2. ✅ Configurar auto-update endpoint
3. ✅ Fazer release v1.0.0
4. ✅ Distribuir link/MSI para usuários
5. ✅ Monitorar feedback
