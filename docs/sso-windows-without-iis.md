# Login Windows sem IIS

O aplicativo desktop pode identificar automaticamente o usuário Windows sem
usar IIS, Kerberos no navegador ou cabeçalhos de proxy.

## Backend local

Quando o React acessa `http://127.0.0.1:8000`, o backend executa `whoami /upn`
na mesma sessão em que foi iniciado pelo Tauri. Esse é o modo `desktop`.

O backend precisa ser executado com a conta do usuário interativo. Não instale
o sidecar como serviço usando `LocalSystem`, pois nesse caso `whoami` retornaria
a conta do serviço.

## Backend central

Quando o React acessa o servidor corporativo, por exemplo
`https://wmt.example.com`, o backend usa exclusivamente o endereço IP direto da
conexão para consultar, via WMI/CIM, o usuário interativo da estação. Esse é o
modo `client-ip`, compatível com o comportamento histórico do WMT.

Requisitos:

- servidor e estação no domínio/rede corporativa;
- WMI/CIM remoto permitido pelo firewall;
- conta do backend com permissão de consulta nas estações;
- resolução e roteamento sem NAT entre servidor e estação;
- HTTPS válido no endpoint central.

O valor de `X-Forwarded-For` enviado diretamente pelo cliente é ignorado. Ele
só participa do cálculo quando a conexão vem de um proxy explicitamente
confiável.

## Configuração

SSO e os dois modos ficam desativados por padrão. Habilite somente os modos
necessários:

```powershell
$env:WMT_SSO_ENABLED = "true"
$env:WMT_SSO_DESKTOP_FALLBACK = "true"
$env:WMT_SSO_CLIENT_IP_FALLBACK = "true"
```

É possível desativar individualmente um modo:

```powershell
$env:WMT_SSO_CLIENT_IP_FALLBACK = "false"
```

Use `WMT_SSO_ALLOWED_GROUPS`, `WMT_SSO_ADMIN_GROUPS` e os demais mapas de
grupos para controlar quem pode entrar e qual papel será atribuído.
`WMT_SSO_ALLOWED_GROUPS` é obrigatório quando o SSO está ativo; sem ele, o
backend recusa o login integrado com erro de configuração.

## Limitação de segurança

O modo central sem IIS confirma qual sessão interativa a própria estação
reporta via WMI/CIM. Ele é adequado como modo de compatibilidade em uma rede
corporativa administrada, mas não substitui uma autenticação criptográfica
Kerberos/Negotiate em redes não confiáveis.
