# IIS + Windows Auth Setup - Checklist Rápido

## ✅ Passos para Configurar IIS com X-Remote-User

### Pré-requisitos
- [ ] Windows Server 2016+ com IIS 10+
- [ ] Módulo `Windows Authentication` instalado
- [ ] Módulo `Application Request Routing (ARR)` instalado
- [ ] Módulo `URL Rewrite` instalado
- [ ] Backend FastAPI rodando em `http://127.0.0.1:8000`

### Instalação de Módulos (PowerShell como Admin)

```powershell
# Windows Authentication
Install-WindowsFeature -Name Web-Windows-Auth

# Verificar ARR: https://www.iis.net/downloads/microsoft/application-request-routing
# Verificar URL Rewrite: https://www.iis.net/downloads/microsoft/url-rewrite
```

### Executar Script de Configuração

```powershell
# Entrar no diretório do projeto
cd C:\Users\...\wmt-desktop

# Executar script de configuração automática (como Admin)
powershell -ExecutionPolicy Bypass -File .\scripts\configure-iis-windows-auth.ps1 `
  -SiteName "WMT" `
  -BackendUrl "http://127.0.0.1:8000" `
  -DomainPrefix "wmt.empresa.local"
```

### Configurar Variáveis de Ambiente

```powershell
# Executar como Admin para definir globalmente
[Environment]::SetEnvironmentVariable('WMT_SSO_ENABLED', 'true', 'Machine')
[Environment]::SetEnvironmentVariable('WMT_SSO_TRUSTED_PROXY_IPS', '127.0.0.1,::1', 'Machine')
[Environment]::SetEnvironmentVariable('WMT_SSO_DEFAULT_ROLE', 'viewer', 'Machine')

# Se deseja limitar por grupos (recomendado em produção):
[Environment]::SetEnvironmentVariable('WMT_SSO_ALLOWED_GROUPS', 'CN=WMT-Users,OU=Groups,DC=empresa,DC=local', 'Machine')
[Environment]::SetEnvironmentVariable('WMT_SSO_ADMIN_GROUPS', 'CN=WMT-Admins,OU=Groups,DC=empresa,DC=local', 'Machine')

# Reiniciar o Application Pool ou o computador
```

### Verificação Manual no IIS Manager (Alternativa)

Se preferir configurar manualmente:

1. **Abra IIS Manager** → Sites → seu-site-WMT
2. **Clique em Authentication**
   - ✓ Habilitar: `Windows Authentication`
   - ✗ Desabilitar: `Anonymous Authentication`
3. **Clique em Windows Authentication** → **Providers**
   - Ordem: `Negotiate` (1º), `NTLM` (2º)
4. **Vá para URL Rewrite** (no site ou no servidor)
   - Criar regra com nome: `Route to WMT Backend`
   - Pattern: `^(.*)$`
   - Rewrite URL: `http://127.0.0.1:8000/{R:1}`
   - Server Variables:
     - `HTTP_X_REMOTE_USER` = `{LOGON_USER}`
     - `HTTP_X_FORWARDED_FOR` = `{REMOTE_ADDR}`
     - `HTTP_X_FORWARDED_PROTO` = `https`

### Testar Configuração

```powershell
# Executar script de teste (como Admin)
.\scripts\test-iis-windows-auth.ps1 -SiteName "WMT"
```

Procure por:
- ✓ Windows Authentication habilitado
- ✓ Anonymous desabilitado
- ✓ Providers: Negotiate, NTLM
- ✓ URL Rewrite configurado
- ✓ HTTP_X_REMOTE_USER em ServerVariables
- ✓ Backend respondendo

### Testar no Navegador

1. Abra: `https://wmt.empresa.local`
2. Você deve receber prompt de autenticação Windows
3. Após autenticar, vê a aplicação

### Testar com curl/PowerShell

```bash
# Teste básico (verá um redirect ou 401 se as credenciais não estiverem em cache)
curl -v -I https://wmt.empresa.local/

# Teste com header simulado (do próprio servidor)
curl -H "X-Remote-User: EMPRESA\seu_usuario" http://127.0.0.1:8000/api/auth/sso
```

### Configurar Kerberos (Opcional, recomendado)

Se o Application Pool usa conta de serviço:

```powershell
# Registrar SPN
setspn -S HTTP/wmt.empresa.local EMPRESA\svc_wmt_app
setspn -S HTTP/wmt EMPRESA\svc_wmt_app

# Verificar
setspn -L EMPRESA\svc_wmt_app

# Verificar duplicatas
setspn -Q HTTP/wmt.empresa.local
```

## 🐛 Troubleshooting

| Problema | Solução |
|----------|---------|
| 401 Unauthorized | Verifique se Windows Auth está **habilitado** e Anonymous **desabilitado** |
| Senha pedida toda vez | Kerberos não funciona, ativando NTLM (ok, mas menos eficiente) |
| Headers não chegam ao backend | Verifique URL Rewrite em `ServerVariables` → `HTTP_X_REMOTE_USER` |
| Backend retorna 500 | Variáveis `SSO_ALLOWED_GROUPS` vazias ou grupo AD incorreto |
| CORS error no navegador | Verifique CORS no FastAPI (`client/` origins) |
| "Site not found" | Verifique DNS, certificado HTTPS, endereço correto |

## 📋 Arquivos Criados

- [docs/iis-windows-auth-setup.md](../docs/iis-windows-auth-setup.md) - Documentação completa
- [scripts/configure-iis-windows-auth.ps1](../scripts/configure-iis-windows-auth.ps1) - Script de configuração automática
- [scripts/test-iis-windows-auth.ps1](../scripts/test-iis-windows-auth.ps1) - Script de teste
- [docs/sso-iis-kerberos.md](../docs/sso-iis-kerberos.md) - Visão geral da arquitetura SSO

## 🔒 Segurança

✅ **Fazer:**
- Nunca exponha FastAPI direto na rede (apenas 127.0.0.1:8000)
- IIS como único proxy reverso autenticado
- Use HTTPS no site IIS
- Configure `WMT_SSO_ALLOWED_GROUPS` em produção

❌ **Não fazer:**
- Deixar FastAPI escutando em 0.0.0.0
- Deixar `WMT_SSO_ALLOWED_GROUPS` vazio (qualquer usuário Windows passa)
- Usar HTTP em produção
- Compartilhar credenciais do AD nos logs

## 📞 Suporte

Para mais detalhes, veja:
- [docs/iis-windows-auth-setup.md](../docs/iis-windows-auth-setup.md)
- [docs/sso-iis-kerberos.md](../docs/sso-iis-kerberos.md)
