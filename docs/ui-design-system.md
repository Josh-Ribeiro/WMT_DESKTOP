# Padrão de UI/UX

Este documento define o padrão visual usado nas telas autenticadas do WMT.
A evolução deve ser incremental: preservar fluxos, rotas e permissões enquanto
as páginas passam a compartilhar a mesma estrutura.

## Princípios

- Priorizar a próxima ação do operador, não apenas exibir dados.
- Mostrar carregamento, erro, conteúdo vazio e sucesso de forma explícita.
- Usar texto curto e operacional em português.
- Manter ações destrutivas identificáveis e sempre confirmadas.
- Preservar navegação por teclado, foco visível e nomes acessíveis.
- Funcionar a partir de 320 px e acomodar escala de exibição do Windows.

## Estrutura de página

Os componentes compartilhados ficam em `client/src/components/PageLayout.tsx`:

- `PageShell`: rolagem, largura máxima e espaçamento responsivo.
- `PageHero`: contexto da tela, título, descrição, metadados e ação principal.
- `SectionHeading`: título, descrição e ação de uma seção.
- `EmptyState`: ausência de conteúdo com orientação e ação opcional.

Uma página autenticada não deve criar outro `h-screen`. O viewport e a
navegação pertencem ao `AuthenticatedLayout`; a página fornece apenas seu
conteúdo dentro de `PageShell`.

## Hierarquia e espaçamento

- Uma única tag `h1` por tela, fornecida por `PageHero`.
- Títulos de seção usam `SectionHeading`.
- Espaçamento entre grandes blocos: 20 px no compacto e 24 px no desktop.
- Padding da página: 16 px no compacto, 24 px em telas médias e 32 px no desktop.
- Conteúdo operacional tem largura máxima de 1440 px.

## Componentes e estados

- Reutilizar os componentes em `components/ui` antes de criar variações locais.
- Usar `Skeleton` para a primeira carga, mantendo a forma aproximada do conteúdo.
- Erros precisam de `role="alert"`, mensagem compreensível e ação de repetição
  quando aplicável.
- Estados vazios explicam por que não há conteúdo e o que acontecerá depois.
- Status não devem depender apenas de cor: incluir rótulo e, quando necessário,
  ícone ou animação.

## Responsividade e acessibilidade

- A navegação lateral permanece visível a partir do breakpoint `md`.
- Abaixo de `md`, a navegação é aberta por um menu lateral modal.
- Elementos interativos precisam de área mínima confortável e foco visível.
- Não usar `button` para conteúdo que não executa ação.
- Respeitar contraste dos tokens de tema claro, escuro e cores de destaque.

## Checklist de migração

1. Trocar o contêiner local por `PageShell`.
2. Trocar o cabeçalho por `PageHero`.
3. Substituir títulos locais por `SectionHeading`.
4. Cobrir carga inicial, erro, vazio e sucesso.
5. Testar larguras de 320, 768, 1024 e 1440 px.
6. Testar navegação por teclado e modo escuro.
7. Executar `pnpm check`, `pnpm test` e `pnpm build`.
