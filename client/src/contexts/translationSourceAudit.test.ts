import fs from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { translateText } from "./LanguageContext";

const portugueseText =
  /[áàâãéêíóôõúç]|\b(?:não|nao|uma|para|pasta|usuário|usuario|usuários|usuarios|origem|destino|selecionar|selecione|abrir|salvar|carregar|falha|erro|modo|equipamento|atualização|atualizações|ações|histórico|termo|termos|cópia|dados|nenhum|nenhuma|informe|remover|gerar|imprimir|concluído|pendente|disponível|configurações|perfis|perfil|chamado|pesquisar|tarefa|tarefas|último|última|detalhes|rápida|rápido|rede|acesso|conta|senha|idioma|bom|boa|operador|rodando|bloqueado|instalado|consultando|clique|resumo|relatório|validação|limpeza|estação|impressora|máquina|migração|copiado|encontrado|autenticação|sessão|serviço|saúde|atenção|revisão|próximo|próxima|progresso|duração|memória|disco|versão|pesquisa|busca)\b/i;

interface Candidate {
  file: string;
  line: number;
  text: string;
}

function sourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(entryPath);
    if (!/\.(ts|tsx)$/.test(entry.name)) return [];
    if (entry.name.includes(".test.") || entry.name === "LanguageContext.tsx")
      return [];
    return [entryPath];
  });
}

function candidatesFrom(file: string, sourceRoot: string): Candidate[] {
  const source = fs.readFileSync(file, "utf8");
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  );
  const candidates: Candidate[] = [];

  const add = (text: string, node: ts.Node) => {
    const normalized = text.replace(/\s+/g, " ").trim();
    if (!normalized || !portugueseText.test(normalized)) return;
    candidates.push({
      file: path.relative(sourceRoot, file).replaceAll("\\", "/"),
      line: sourceFile.getLineAndCharacterOfPosition(node.pos).line + 1,
      text: normalized,
    });
  };

  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      add(node.text, node);
    } else if (
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node)
    ) {
      add(node.text, node);
    } else if (ts.isTemplateExpression(node)) {
      let sample = node.head.text;
      for (const span of node.templateSpans) {
        sample += `1${span.literal.text}`;
      }
      add(sample, node);
    }
    ts.forEachChild(node, visit);
  };

  visit(sourceFile);
  return candidates;
}

describe("Portuguese to English source coverage", () => {
  it("translates every Portuguese UI string or dynamic template", () => {
    const sourceRoot = path.resolve(import.meta.dirname, "..");
    const candidates = sourceFiles(sourceRoot).flatMap(file =>
      candidatesFrom(file, sourceRoot)
    );
    const missing = candidates
      .filter(
        candidate => translateText(candidate.text, "en-US") === candidate.text
      )
      .map(
        candidate =>
          `${candidate.file}:${candidate.line} — ${JSON.stringify(candidate.text)}`
      );

    expect(missing).toEqual([]);
  });
});
