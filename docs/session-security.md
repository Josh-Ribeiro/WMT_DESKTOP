# Sessão, cookies e CSRF

O frontend não armazena mais credenciais em `localStorage`. A sessão é
identificada por um cookie `HttpOnly`, limitado a `/api`, e o JavaScript mantém
somente um token CSRF em memória.

## Produção

O padrão de produção é:

```powershell
$env:WMT_SESSION_COOKIE_SECURE = "true"
$env:WMT_SESSION_COOKIE_SAMESITE = "none"
$env:WMT_ALLOW_BEARER_AUTH = "false"
```

`SameSite=None` é necessário quando o WebView e a API HTTPS são considerados
sites diferentes. Ele somente é aceito com `Secure=true`.

O frontend envia `credentials: include` e acrescenta `X-CSRF-Token` às
operações que modificam estado. O token CSRF é recuperado no login/SSO e em
`GET /api/auth/me`, portanto uma recarga da aplicação não exige persistência no
JavaScript.

O backend aceita somente as origens exatas do Tauri e as origens configuradas
em `WMT_CORS_ORIGINS`. Origem `null` e localhost em portas arbitrárias não são
aceitos em produção. Métodos e cabeçalhos CORS também usam uma lista explícita.

O login local limita, por combinação de endereço do cliente e usuário, cinco
falhas em cinco minutos. Os limites podem ser ajustados com
`WMT_LOGIN_RATE_LIMIT_MAX_ATTEMPTS` e
`WMT_LOGIN_RATE_LIMIT_WINDOW_SECONDS`.

## Desenvolvimento local

Ao iniciar o backend com `WMT_DEV=1`, o padrão muda para cookie sem `Secure` e
`SameSite=Lax`, permitindo `http://127.0.0.1:8000`.

```powershell
$env:WMT_DEV = "1"
python backend/main.py
```

## Compatibilidade bearer

Integrações legadas podem habilitar temporariamente
`WMT_ALLOW_BEARER_AUTH=true`. Essa opção fica desativada por padrão e não é
usada pelo frontend.

## HTTPS e atualizador

Builds de produção exigem URL HTTPS. O script de release rejeita endpoint HTTP
para atualizações, o Tauri não permite transporte inseguro e a CSP limita as
conexões aos origins configurados durante o build.
