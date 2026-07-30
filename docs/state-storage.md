# Persistência e bootstrap

O estado operacional do backend é armazenado em SQLite. O caminho padrão é
`backend/data/state.db` e pode ser alterado por `WMT_STATE_DB_PATH`.

## Migração do JSON

Na primeira inicialização, se o banco ainda não possuir um snapshot e existir
`backend/data/state.json`, seu conteúdo é importado automaticamente. O JSON é
mantido como cópia legada e deixa de receber atualizações.

A migração também:

- remove o registro demonstrativo `BK001` quando ele corresponde exatamente ao
  fixture antigo;
- bloqueia contas que ainda utilizam `admin123`;
- substitui a senha legada somente quando
  `WMT_BOOTSTRAP_ADMIN_PASSWORD` estiver configurada para o mesmo usuário.

## Primeiro administrador local

Não existe administrador padrão. Antes da primeira inicialização, configure:

```powershell
$env:WMT_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:WMT_BOOTSTRAP_ADMIN_PASSWORD = "uma-senha-inicial-exclusiva"
$env:WMT_BOOTSTRAP_ADMIN_EMAIL = "wmt-admin@empresa.local"
```

A senha deve possuir pelo menos 12 caracteres e não pode ser `admin123`.
Depois de validar o primeiro acesso, remova o segredo do ambiente do serviço.

Em instalações exclusivamente SSO, as variáveis de bootstrap podem permanecer
ausentes e os usuários serão provisionados pelas regras SSO.

## Concorrência

O SQLite usa WAL, sincronização completa, transações de escrita e revisão
otimista do snapshot. Uma gravação baseada em uma revisão antiga é rejeitada em
vez de sobrescrever silenciosamente alterações mais recentes.

## Auditoria

Eventos de auditoria ficam na tabela dedicada `audit_log`, com índices por data
e ação. Cada evento é inserido em sua própria transação e o armazenamento não
aplica limite de quantidade. Na atualização para o schema 3, eventos ainda
presentes no campo `audit` do snapshot são migrados automaticamente e removidos
do JSON interno.
