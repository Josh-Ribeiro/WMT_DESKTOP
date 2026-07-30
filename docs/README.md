# Documentação do WMT

Os documentos mantidos como referência oficial são:

- [Desenvolvimento e instalação](../SETUP.md)
- [Arquitetura](../ARCHITECTURE.md)
- [Testes](../TEST_GUIDE.md)
- [Runtime central e sidecar](backend-runtime.md)
- [Armazenamento SQLite](state-storage.md)
- [Sessão e CSRF](session-security.md)
- [Autorização no React](frontend-authorization.md)
- [Padrão de UI/UX](ui-design-system.md)
- [Login Windows sem IIS](sso-windows-without-iis.md)
- [IIS opcional com Windows Authentication](iis-windows-auth-setup.md)
- [Build e atualização automática](auto-update.md)
- [Migração do servidor](wmt-server-migration.md)

Orientações antigas de build, distribuição e gerenciamento do backend foram
removidas para evitar instruções concorrentes. O fluxo de release oficial é
`scripts/build-and-release.ps1`.
