# WMT em modo de desenvolvimento

Não é necessário gerar MSI nem executar build para testar alterações.

## Aplicativo desktop (recomendado)

Na raiz do projeto:

```powershell
pnpm dev:tauri
```

Esse comando abre o WMT Desktop em modo debug. O frontend usa hot reload do
Vite e o backend reinicia automaticamente quando um arquivo Python é alterado.
Alterações no PowerShell são usadas na próxima execução da ação, sem rebuild.

Encerre com `Ctrl+C`. Não mantenha outra instância do backend usando a porta
8000, pois o Tauri reutiliza qualquer processo que já esteja nessa porta.

## Somente navegador

Abra dois terminais na raiz do projeto.

Terminal 1:

```powershell
pnpm dev:backend
```

Terminal 2:

```powershell
pnpm dev:web
```

Depois acesse `http://localhost:5173`.

## Quando ainda é necessário build

Use `pnpm build:tauri` apenas para validar ou publicar o instalador final.
