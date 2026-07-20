# Configurar IIS para Windows Authentication + X-Remote-User

## Pré-requisitos

- IIS instalado em Windows Server 2016+
- módulo `Windows Authentication` instalado no IIS
- módulo `Application Request Routing (ARR)` instalado (versão 3.2+)
- módulo `URL Rewrite` instalado (versão 2.1+)
- Site HTTPS configurado com certificado válido
- Backend FastAPI rodando localmente em `http://127.0.0.1:8000`

## 1. Instalar módulos IIS necessários

Execute como Administrator:

```powershell
# Instalar Windows Authentication
Install-WindowsFeature -Name Web-Windows-Auth

# Instalar Application Request Routing (ARR)
# Baixe em: https://www.iis.net/downloads/microsoft/application-request-routing
# Ou instale via script se disponível

# Instalar URL Rewrite
# Baixe em: https://www.iis.net/downloads/microsoft/url-rewrite
```

## 2. Configurar o Site no IIS Manager

### 2.1 - Desabilitar Anonymous, habilitar Windows Auth

```
IIS Manager → Sites → seu-site-wmt
→ Authentication
  ✓ Windows Authentication (Habilitado)
  ✗ Anonymous Authentication (Desabilitado)
  ✗ Outros (deixe desabilitados)
```

### 2.2 - Configurar Windows Authentication Providers

Clique em `Windows Authentication` → `Providers`:

```
1. Negotiate (primeiro)
2. NTLM (segundo - fallback)
```

Remova qualquer outro provider se existir.

### 2.3 - Habilitar Extended Protection

Clique em `Windows Authentication` → `Advanced Settings`:

```
Extended Protection: Accept
```

## 3. Configurar Application Request Routing (ARR) + URL Rewrite

### 3.1 - Definir Server Farm

```
IIS Manager → Server Farms (raiz)
→ Create Server Farm...

Name: "wmt-backend"
Add Server: http://127.0.0.1:8000
```

### 3.2 - Configurar Rewrite Rules

No seu site WMT, vá para `URL Rewrite` e adicione:

**Rule 1: Rewrite para Backend**

```
Rule Name: "Route to WMT Backend"
Pattern: ^(.*)$
Rewrite URL: http://127.0.0.1:8000/{R:1}
Append query string: ✓
```

### 3.3 - Passar Headers de Autenticação

Na mesma Rewrite Rule, vá para `Edit` → `Server Variables` e adicione:

```
HTTP_X_REMOTE_USER = {LOGON_USER}
HTTP_X_FORWARDED_FOR = {REMOTE_ADDR}
HTTP_X_FORWARDED_PROTO = https
HTTP_X_FORWARDED_HOST = {HTTP_HOST}
```

## 4. Configuração via web.config (Alternativa/Confirmação)

Se preferir editar manualmente, edite o `web.config` do site WMT:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    
    <!-- Authentication -->
    <authentication>
      <windowsAuthentication enabled="true">
        <providers>
          <add value="Negotiate" />
          <add value="NTLM" />
        </providers>
      </windowsAuthentication>
      <anonymousAuthentication enabled="false" />
    </authentication>

    <!-- URL Rewrite -->
    <rewrite>
      <rules>
        <rule name="Route to WMT Backend" enabled="true" stopProcessing="true">
          <match url="^(.*)$" />
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" />
          <serverVariables>
            <set name="HTTP_X_REMOTE_USER" value="{LOGON_USER}" />
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
          </serverVariables>
        </rule>
      </rules>
    </rewrite>

    <!-- CORS e Headers -->
    <httpProtocol>
      <customHeaders>
        <add name="Access-Control-Allow-Origin" value="https://seu-dominio.local" />
        <add name="Access-Control-Allow-Credentials" value="true" />
      </customHeaders>
    </httpProtocol>
    
  </system.webServer>
</configuration>
```

## 5. Configurar Backend FastAPI

Verifique que as variáveis de ambiente estão definidas:

```powershell
# No Application Pool ou em variáveis globais:
$env:WMT_SSO_ENABLED = "true"
$env:WMT_SSO_TRUSTED_PROXY_IPS = "127.0.0.1,::1"
$env:WMT_SSO_ALLOWED_GROUPS = "CN=WMT-Users,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_ADMIN_GROUPS = "CN=WMT-Admins,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_DEFAULT_ROLE = "viewer"
```

## 6. Kerberos SPN (se usar Application Pool com conta de serviço)

Se o application pool roda com conta `EMPRESA\svc_wmt`:

```powershell
# Registrar SPN
setspn -S HTTP/wmt.empresa.local EMPRESA\svc_wmt
setspn -S HTTP/wmt EMPRESA\svc_wmt

# Verificar
setspn -L EMPRESA\svc_wmt
```

Evite duplicatas:
```powershell
setspn -Q HTTP/wmt.empresa.local
```

## 7. Testar Fluxo

### 7.1 - Verificar Header no IIS

Instale `Failed Request Tracing`:
```powershell
Install-WindowsFeature -Name Web-Req-Monitoring
```

Configure regra para rastrear headers, acesse o site e verifique os logs em `%WINDIR%\System32\LogFiles\FailedReqLogFiles`.

### 7.2 - Testar com curl do servidor

```bash
# Do próprio servidor IIS, com credenciais cached
curl -v https://wmt.empresa.local/
```

Procure por:
- `WWW-Authenticate: Negotiate`
- Request retorna 200 (não 401)

### 7.3 - Testar Backend diretamente

```bash
curl -v \
  -H "X-Remote-User: EMPRESA\seu_usuario" \
  http://127.0.0.1:8000/api/auth/sso
```

Esperado: 200 + token JWT

## 8. Solução de Problemas

| Sintoma | Causa | Solução |
|---------|-------|---------|
| 401 Unauthorized | Windows Auth não habilitado ou credenciais erradas | Verifique `Authentication` → `Windows Authentication` está habilitado |
| Headers não chegam ao backend | URL Rewrite não está passando | Verifique `ServerVariables` na regra de rewrite |
| Kerberos não funciona, cai para NTLM | SPN não configurado ou resolvível | Configure SPN, verifique DNS, teste `setspn -Q` |
| CORS error no navegador | Origins não configuradas | Adicione origem no FastAPI CORS ou em `web.config` |
| 500 no backend | AD não resolvível, grupos incorretos | Verifique variáveis `SSO_ALLOWED_GROUPS`, teste acesso AD |

## 9. Segurança

- ✓ Nunca exponha FastAPI direto na rede aceitando headers SSO
- ✓ Backend deve escutar apenas `127.0.0.1:8000` ou rede protegida
- ✓ Configure HTTPS no site IIS
- ✓ Defina `WMT_SSO_ALLOWED_GROUPS` em produção (nunca deixe vazio)
- ✓ Use `X-Forwarded-*` para logs corretos

## 10. Referência Rápida: Headers

Backend aceita qualquer um desses headers (primeiro encontrado):
- `X-Remote-User`
- `X-Windows-User`
- `X-IIS-WinAuth-User`
- `REMOTE_USER` (CGI)

Configure no IIS em `ServerVariables`:
```xml
<set name="HTTP_X_REMOTE_USER" value="{LOGON_USER}" />
```
