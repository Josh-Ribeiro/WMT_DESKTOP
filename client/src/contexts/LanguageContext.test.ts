import { describe, expect, it } from "vitest";
import { translateText } from "./LanguageContext";

const portugueseCoverage = [
  "User Management",
  "Manage system users and permissions",
  "Add User",
  "Create a new user account",
  "Responsibility and acceptance",
  "Equipment return",
  "Generate DOCX",
  "Print Preview",
  "Remote Tasks",
  "Create Temp C Share",
  "Computer Management",
  "Backup pre-check",
  "Failed to start backup",
  "Running",
  "Scheduled",
  "Viewer",
  "Administrator",
  "Locked",
  "Page Not Found",
  "Reload Page",
  "Invalid credentials",
  "Session expired",
  "Invalid CSRF token",
] as const;

const englishCoverage = [
  "Ações e atualizações",
  "Ambiente estável",
  "Ativar modo manutenção",
  "Busca rápida",
  "Carregar usuários",
  "Destino dos perfis",
  "Escolha entre migração de perfis ou cópia de uma pasta específica.",
  "Modos de manutenção ativos",
  "Nenhum modo de manutenção ativo agora.",
  "Pasta customizada",
  "Pasta de origem",
  "Pasta de destino",
  "Perfis selecionados",
  "Selecionar pasta",
  "Troca de máquina",
  "Usuários encontrados",
] as const;

describe("interface translations", () => {
  it.each(portugueseCoverage)("translates %s to Portuguese", source => {
    expect(translateText(source, "pt-BR")).not.toBe(source);
  });

  it("preserves whitespace around translated text", () => {
    expect(translateText("  Add User  ", "pt-BR")).toBe(
      "  Adicionar usuário  "
    );
  });

  it("translates dynamic interface messages", () => {
    expect(translateText("Users (42)", "pt-BR")).toBe("Usuários (42)");
    expect(translateText("WMT 1.2.3 is available", "pt-BR")).toBe(
      "A versão 1.2.3 do WMT está disponível"
    );
    expect(
      translateText("Downloading WMT 1.2.3 (3 MB / 8 MB)...", "pt-BR")
    ).toBe("Baixando WMT 1.2.3 (3 MB / 8 MB)...");
    expect(translateText("Inventory completed", "pt-BR")).toBe(
      "Inventory concluído"
    );
  });

  it("translates catalog entries back when English is selected", () => {
    const portuguese = translateText("User Management", "pt-BR");
    expect(translateText(portuguese, "en-US")).toBe("User Management");
  });

  it.each(englishCoverage)("translates %s to English", source => {
    expect(translateText(source, "en-US")).not.toBe(source);
  });

  it("translates dynamic Portuguese messages", () => {
    expect(
      translateText("Informe o computador de origem primeiro.", "en-US")
    ).toBe("Enter the source workstation first.");
    expect(translateText("Remover D:\\Backup", "en-US")).toBe(
      "Remove D:\\Backup"
    );
  });

  it("translates the complete dynamic Dashboard copy", () => {
    expect(translateText("Boa tarde", "en-US")).toBe("Good afternoon");
    expect(translateText(", operador", "en-US")).toBe(", operator");
    expect(translateText("Sistema conectado", "en-US")).toBe(
      "System connected"
    );
    expect(translateText("Backups hoje", "en-US")).toBe("Backups today");
    expect(
      translateText("2 remota(s), 2 update(s), 0 backup(s)", "en-US")
    ).toBe("2 remote task(s), 2 update(s), 0 backup(s)");
    expect(translateText("1 falha(s), 0 concluído(s)", "en-US")).toBe(
      "1 failed, 0 completed"
    );
    expect(translateText("0 rodando, 0 falha(s)", "en-US")).toBe(
      "0 running, 0 failed"
    );
    expect(translateText("1 usuário(s) ativo(s)", "en-US")).toBe(
      "1 active user(s)"
    );
  });

  it("translates Portuguese API errors shown by the interface", () => {
    expect(
      translateText("Limite de 3 ações remotas simultâneas atingido.", "en-US")
    ).toBe("The limit of 3 simultaneous remote actions has been reached.");
    expect(
      translateText("PowerShell nao encontrado neste ambiente.", "en-US")
    ).toBe("PowerShell was not found in this environment.");
    expect(
      translateText(
        "Backups estão desabilitados nas configurações do WMT.",
        "en-US"
      )
    ).toBe("Backups are disabled in WMT settings.");
  });

  it("leaves technical and unknown content untouched", () => {
    expect(translateText("GPUpdate", "pt-BR")).toBe("GPUpdate");
    expect(translateText("WK5048-315BR", "pt-BR")).toBe("WK5048-315BR");
  });
});
