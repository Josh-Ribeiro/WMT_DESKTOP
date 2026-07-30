# Autenticação e autorização no frontend

O React possui três camadas centrais:

1. `AuthProvider` restaura e mantém a sessão.
2. `AuthenticationGuard` impede acesso sem usuário autenticado.
3. `PermissionGuard` aplica a política da rota antes de renderizar a página.

O backend continua sendo a autoridade final. Os guards do frontend melhoram a
navegação e evitam que telas sem permissão sejam montadas, mas não substituem
as dependências de autorização do FastAPI.

## Política de rotas

`client/src/lib/routePolicy.ts` é a fonte única para:

- caminho;
- nome apresentado no menu;
- permissão exigida;
- eventual restrição adicional de papel;
- presença ou ausência na navegação lateral.

O `Sidebar` e o roteador consomem a mesma política. Uma rota não deve fazer
redirecionamentos próprios para `/login` nem repetir verificações de papel.

Rotas administrativas exigem simultaneamente a permissão correspondente e o
papel `admin`. Ferramentas secundárias usam a capacidade principal:

- AD Users e Host Performance: `monitor`;
- Machine Replacement: `backup`;
- Workstation History: `history`.

## Layout

`AuthenticatedLayout` monta uma única barra lateral e a área de conteúdo.
Logout global fica no `Sidebar`; a página de conta também oferece um botão
explícito para a mesma ação.

## Testes

```powershell
corepack pnpm test
corepack pnpm check
corepack pnpm build
```

Os testes cobrem a matriz viewer/operator/admin, rotas administrativas,
permissão dedicada de histórico e ferramentas secundárias.
