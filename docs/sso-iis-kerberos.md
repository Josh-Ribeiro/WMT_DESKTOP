# WMT SSO com IIS, Kerberos/NTLM e Active Directory

## Visao Geral

O WMT usa o IIS como camada de Integrated Windows Authentication. O IIS autentica o usuario com Kerberos/NTLM e encaminha a identidade Windows para o backend FastAPI por um header interno.

No pacote desktop/Tauri, quando o backend roda localmente na sessao do usuario, o WMT tambem aceita fallback local: se nao houver header do IIS e a chamada vier de `127.0.0.1`, o backend executa `whoami /upn` ou `whoami` para descobrir a conta Windows atual e aplica a mesma validacao de grupos no AD.

Fluxo:

1. Usuario acessa `https://wmt.empresa.local`.
2. IIS responde com `WWW-Authenticate: Negotiate`.
3. Navegador usa a sessao Windows do usuario.
4. IIS valida no Active Directory.
5. IIS encaminha para o backend local com `X-Remote-User`.
6. FastAPI consulta o AD, valida grupos e gera o token WMT.
7. React consome `/api/auth/sso` e depois `/api/auth/me`.

## Variaveis de Ambiente

```powershell
$env:WMT_SSO_ENABLED="true"
$env:WMT_SSO_TRUSTED_PROXY_IPS="127.0.0.1,::1"
$env:WMT_SSO_DESKTOP_FALLBACK="true"
$env:WMT_SSO_ALLOWED_GROUPS="CN=WMT-Users,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_ADMIN_GROUPS="CN=WMT-Admins,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_OPERATOR_GROUPS="CN=WMT-Operators,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_VIEWER_GROUPS="CN=WMT-Viewers,OU=Groups,DC=empresa,DC=local"
$env:WMT_SSO_DEFAULT_ROLE="viewer"
```

Se `WMT_SSO_ALLOWED_GROUPS` ficar vazio, qualquer usuario Windows autenticado pelo IIS passa pela etapa de acesso. Em producao, configure esse grupo.

## Certificado em Trusted People

Certificado em `Trusted People` normalmente resolve confianca do aplicativo, assinatura do instalador/MSI/MSIX/ClickOnce, ou HTTPS local/self-signed. Ele nao substitui Kerberos/NTLM.

- Modo web/IIS: certificado HTTPS confiavel ajuda o navegador a tratar o site como confiavel/intranet, mas a identidade vem do Windows Authentication do IIS.
- Modo desktop/Tauri: a identidade vem da sessao local via `whoami`, desde que o backend rode como o usuario logado. Certificado pode continuar sendo necessario para distribuicao/assinatura, mas nao e o mecanismo de login.

## IIS

1. Instale `Windows Authentication`.
2. No site do WMT:
   - Desabilite `Anonymous Authentication`.
   - Habilite `Windows Authentication`.
3. Em providers, deixe:
   - `Negotiate`
   - `NTLM`
4. Use ARR/URL Rewrite para proxy para `http://127.0.0.1:8000`.
5. Encaminhe o usuario autenticado para o FastAPI como:
   - `X-Remote-User: {LOGON_USER}`

O backend aceita tambem:

- `X-Windows-User`
- `X-IIS-WinAuth-User`

## SPN Kerberos

Se o application pool roda com uma conta de servico:

```cmd
setspn -S HTTP/wmt.empresa.local EMPRESA\svc_wmt_app
setspn -S HTTP/wmt EMPRESA\svc_wmt_app
setspn -L EMPRESA\svc_wmt_app
```

Evite SPN duplicado:

```cmd
setspn -Q HTTP/wmt.empresa.local
```

## Navegador

Para Edge/Chrome em dominio, normalmente basta o site estar na zona Intranet. Caso necessario, configure via GPO:

- `AuthServerAllowlist`: `wmt.empresa.local`
- `AuthNegotiateDelegateAllowlist`: apenas se houver delegacao/double-hop.

## Backend

Nunca exponha o FastAPI direto na rede aceitando headers SSO. O backend deve escutar apenas em `127.0.0.1` ou em rede protegida pelo proxy IIS.

## Kerberos x NTLM

Kerberos e o preferido em Active Directory: usa tickets, SPN e suporta cenarios modernos. NTLM e fallback legado, mais limitado e deve ser evitado quando Kerberos funciona.
