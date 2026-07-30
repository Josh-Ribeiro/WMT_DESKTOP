import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { apiFetch } from "@/lib/api";

export type DisplayLanguage = "en-US" | "pt-BR";

interface LanguageContextValue {
  language: DisplayLanguage;
  setLanguage: (language: DisplayLanguage) => void;
  t: (text: string) => string;
}

const STORAGE_KEY = "wmt_display_language";

const enToPt: Record<string, string> = {
  Dashboard: "Painel",
  Monitor: "Monitor",
  Tasks: "Tarefas",
  Backup: "Backup",
  "WK History": "Histórico WK",
  Terms: "Termos",
  Users: "Usuários",
  "Admin Settings": "Configurações de administrador",
  Settings: "Configurações",
  "Command Center": "Central de comando",
  "Logged in as": "Logado como",
  Logout: "Sair",
  Refresh: "Atualizar",
  Save: "Salvar",
  "Saving...": "Salvando...",
  "Operational settings for WMT.": "Configurações operacionais do WMT.",
  "Interface language": "Idioma da interface",
  "Choose the language used by WMT on this workstation.":
    "Escolha o idioma usado pelo WMT nesta workstation.",
  Language: "Idioma",
  English: "Inglês",
  Portuguese: "Português",
  "Timeouts and polling": "Timeouts e polling",
  "Enabled scripts": "Scripts habilitados",
  "Default destination path": "Caminho padrão de destino",
  "Remote action aliases": "Aliases de ações remotas",
  "Simple JSON. Example:": "JSON simples. Exemplo:",
  "Settings saved": "Configurações salvas",
  "Failed to save settings": "Falha ao salvar configurações",
  "Check the fields and try again.": "Verifique os campos informados.",
  "Diagnostic log": "Log de diagnóstico",
  "Visual diagnostic package": "Pacote visual de diagnóstico",
  "Detailed inventory": "Inventário detalhado",
  Cleanup: "Limpeza",
  System: "Sistema",
  "Disks and BitLocker": "Discos e BitLocker",
  "Installed software": "Softwares instalados",
  "Software Center": "Software Center",
  "Remote Actions": "Ações remotas",
  "Quick Actions": "Ações rápidas",
  "Generating visual diagnostic...": "Gerando diagnóstico visual...",
  "Consulting...": "Consultando...",
  "No disk returned.": "Nenhum disco retornado.",
  "No installed software returned.": "Nenhum software instalado retornado.",
  "No user profiles were found on the source workstation.":
    "Nenhum perfil de usuário foi encontrado na workstation de origem.",
  "Current Password": "Senha atual",
  "New Password": "Nova senha",
  "Confirm Password": "Confirmar senha",
  "Enter current password": "Informe a senha atual",
  "Enter new password": "Informe a nova senha",
  "Confirm new password": "Confirme a nova senha",
  "Search Users": "Pesquisar usuários",
  "Search by username or email...": "Pesquisar por usuário ou email...",
  Email: "Email",
  Role: "Perfil",
  Password: "Senha",
  "Enter username": "Informe o usuário",
  "Enter email": "Informe o email",
  "Enter password": "Informe a senha",
  Destination: "Destino",
  History: "Histórico",
  Start: "Início",
  Source: "Origem",
  Status: "Status",
  Host: "Host",
  "Remote Tasks": "Tarefas remotas",
  Total: "Total",
  Active: "Ativo",
  Completed: "Concluído",
  Failed: "Falhou",
  Canceled: "Cancelado",
  "Workstation History": "Histórico da workstation",
  "Remote actions": "Ações remotas",
  Diagnostics: "Diagnósticos",
  Errors: "Erros",
  Workstation: "Workstation",
  Hostname: "Hostname",
  "IP Address": "Endereço IP",
  "MAC Address": "Endereço MAC",
  "Last Boot": "Último boot",
  Manufacturer: "Fabricante",
  Model: "Modelo",
  "Serial Number": "Número de série",
  "Operating System": "Sistema operacional",
  Processor: "Processador",
  Updates: "Atualizações",
  "Selected host:": "Host selecionado:",
  "Enter a workstation first.": "Informe uma workstation primeiro.",
  "DOCX generated and ready": "DOCX gerado e pronto",
  "Employee full name": "Nome completo do funcionário",
  Name: "Nome",
  "Print preview is not ready yet.":
    "A prévia de impressão ainda não está pronta.",
  "Account details, access profile and WMT appearance preferences.":
    "Detalhes da conta, perfil de acesso e preferências visuais do WMT.",
  "Local account": "Conta local",
  Profile: "Perfil",
  "Current identity used by WMT.": "Identidade atual usada pelo WMT.",
  "Display name": "Nome de exibição",
  Username: "Usuário",
  Domain: "Domínio",
  Local: "Local",
  "Not available": "Não disponível",
  Permissions: "Permissões",
  "No explicit permissions loaded.": "Nenhuma permissão explícita carregada.",
  Session: "Sessão",
  "Current authentication state.": "Estado atual da autenticação.",
  "Authenticated with your Windows account.":
    "Autenticado com sua conta Windows.",
  "Authenticated with a local WMT account.":
    "Autenticado com uma conta local do WMT.",
  "Access is controlled by your role and available permissions.":
    "O acesso é controlado pelo seu perfil e permissões disponíveis.",
  Appearance: "Aparência",
  "Choose how WMT should look on this workstation.":
    "Escolha como o WMT deve aparecer nesta workstation.",
  "Dark mode": "Modo escuro",
  "Use a darker interface for low-light environments.":
    "Use uma interface mais escura para ambientes com pouca luz.",
  "Accent color": "Cor de destaque",
  "This changes buttons, selected navigation and focus color.":
    "Isto altera botões, navegação selecionada e cor de foco.",
  Blue: "Azul",
  Violet: "Violeta",
  Pink: "Rosa",
  Emerald: "Esmeralda",
  Cyan: "Ciano",
  Amber: "Âmbar",
  Preview: "Prévia",
  "Primary action": "Ação primária",
  Secondary: "Secundária",
  Selected: "Selecionado",
  Security: "Segurança",
  "Password is managed by Active Directory for this session.":
    "A senha é gerenciada pelo Active Directory nesta sessão.",
  "Manage your local WMT password.": "Gerencie sua senha local do WMT.",
  "Windows account security": "Segurança da conta Windows",
  "Password changes should be done through Windows/Active Directory policies.":
    "Alterações de senha devem ser feitas pelas políticas do Windows/Active Directory.",
  "Update Password": "Atualizar senha",
  "Please fill in all password fields": "Preencha todos os campos de senha",
  "New passwords do not match": "As novas senhas não conferem",
  "Password must be at least 8 characters long":
    "A senha deve ter pelo menos 8 caracteres",
  "Password changed successfully": "Senha alterada com sucesso",
  "Failed to change password": "Falha ao alterar senha",
  "Remote action canceled by user.": "Ação remota cancelada pelo usuário.",
  "Running remote action...": "Executando ação remota...",
  "Remote action added to queue.": "Ação remota adicionada à fila.",
  "User Management": "Gerenciamento de usuários",
  "Manage system users and permissions":
    "Gerencie usuários e permissões do sistema",
  "Total Users": "Total de usuários",
  "Active Users": "Usuários ativos",
  "Add User": "Adicionar usuário",
  "Manage all system users": "Gerencie todos os usuários do sistema",
  "No users found": "Nenhum usuário encontrado",
  "Edit User": "Editar usuário",
  "Delete user": "Excluir usuário",
  Edit: "Editar",
  Unlock: "Desbloquear",
  Lock: "Bloquear",
  Delete: "Excluir",
  Confirm: "Confirmar",
  Cancel: "Cancelar",
  Create: "Criar",
  Update: "Atualizar",
  "Create a new user account": "Crie uma nova conta de usuário",
  "Update user information": "Atualize as informações do usuário",
  "User created successfully": "Usuário criado com sucesso",
  "User updated successfully": "Usuário atualizado com sucesso",
  "User deleted successfully": "Usuário excluído com sucesso",
  "User locked": "Usuário bloqueado",
  "User unlocked": "Usuário desbloqueado",
  "Failed to save user": "Falha ao salvar usuário",
  "Failed to delete user": "Falha ao excluir usuário",
  "Failed to lock user": "Falha ao bloquear usuário",
  "Failed to unlock user": "Falha ao desbloquear usuário",
  "Creating new user...": "Criando novo usuário...",
  "Updating user...": "Atualizando usuário...",
  "Deleting user...": "Excluindo usuário...",
  "Locking user...": "Bloqueando usuário...",
  "Unlocking user...": "Desbloqueando usuário...",
  "Responsibility and acceptance": "Responsabilidade e aceitação",
  "Equipment return": "Devolução de equipamento",
  "Responsibility and return terms": "Termos de responsabilidade e devolução",
  "Generate responsibility and return documents from workstation inventory data.":
    "Gere documentos de responsabilidade e devolução usando os dados do equipamento.",
  Type: "Tipo",
  "Generate DOCX": "Gerar DOCX",
  Download: "Baixar",
  Print: "Imprimir",
  Close: "Fechar",
  "Print Preview": "Prévia de impressão",
  "Download original DOCX": "Baixar DOCX original",
  "Document generation": "Geração do documento",
  "WMT reads the WK data and prepares the DOCX. Use Download when you want to save it.":
    "O WMT consulta os dados da WK e prepara o DOCX. Use Baixar para salvá-lo.",
  "Filled fields": "Campos preenchidos",
  "Selected template": "Modelo selecionado",
  "Loading template path...": "Carregando caminho do modelo...",
  "Template is not accessible from this machine.":
    "O modelo não está acessível nesta máquina.",
  "Fill in the workstation and generate the document directly.":
    "Informe a workstation e gere o documento diretamente.",
  "Preparing print preview...": "Preparando prévia de impressão...",
  "Print preview ready.": "Prévia de impressão pronta.",
  "Loading WK data and generating DOCX...":
    "Carregando dados da WK e gerando DOCX...",
  "Rendering DOCX preview...": "Renderizando prévia do DOCX...",
  "Failed to render DOCX preview.": "Falha ao renderizar a prévia do DOCX.",
  "Failed to prepare print preview.":
    "Falha ao preparar a prévia de impressão.",
  "Failed to generate DOCX.": "Falha ao gerar o DOCX.",
  "DOCX ready. Use Download to save it or Print to print.":
    "DOCX pronto. Use Baixar para salvar ou Imprimir para imprimir.",
  "Remote task canceled": "Tarefa remota cancelada",
  "Remote task created": "Tarefa remota criada",
  "Open Tasks": "Abrir tarefas",
  Open: "Abrir",
  Running: "Em execução",
  Queued: "Na fila",
  Scheduled: "Agendada",
  Updating: "Atualizando",
  Warning: "Alerta",
  Critical: "Crítico",
  Online: "Online",
  Offline: "Offline",
  Viewer: "Visualizador",
  Operator: "Operador",
  Administrator: "Administrador",
  Inactive: "Inativo",
  Locked: "Bloqueado",
  Manual: "Manual",
  "Users (": "Usuários (",
  "Create Temp C Share": "Criar compartilhamento Temp C",
  "Remove Temp C Share": "Remover compartilhamento Temp C",
  "Remote Access": "Acesso remoto",
  "Remote Assistance": "Assistência remota",
  "Computer Management": "Gerenciamento do computador",
  "Restart Spooler": "Reiniciar spooler",
  "Renew IP": "Renovar IP",
  "Force All Actions": "Forçar todas as ações",
  "Clear SCCM Cache": "Limpar cache do SCCM",
  "Backup started": "Backup iniciado",
  "Cancel requested": "Cancelamento solicitado",
  "Backup removed": "Backup removido",
  "No users loaded": "Nenhum usuário carregado",
  "Failed to load users": "Falha ao carregar usuários",
  "Failed to open destination": "Falha ao abrir o destino",
  "Failed to run backup pre-check": "Falha ao executar o pré-check do backup",
  "Failed to simulate backup": "Falha ao simular o backup",
  "Failed to start backup": "Falha ao iniciar o backup",
  "Failed to cancel backup": "Falha ao cancelar o backup",
  "Failed to delete backup": "Falha ao excluir o backup",
  "Failed to load backup details": "Falha ao carregar os detalhes do backup",
  "Failed to start retry": "Falha ao iniciar nova tentativa",
  "Failed to clean backup history": "Falha ao limpar o histórico de backup",
  "Failed to update backup progress":
    "Falha ao atualizar o progresso do backup",
  "Fill source workstation first.": "Informe primeiro a workstation de origem.",
  "Fill destination workstation first.":
    "Informe primeiro a workstation de destino.",
  "Fill backup details and select at least one user.":
    "Preencha os dados do backup e selecione pelo menos um usuário.",
  "Pre-check has blocking issues. Fix them before starting the backup.":
    "O pré-check possui bloqueios. Corrija-os antes de iniciar o backup.",
  "Simulation is available for profile backups.":
    "A simulação está disponível para backups de perfis.",
  "Custom folder backup validates source/destination when the job starts.":
    "O backup de pasta personalizada valida origem e destino ao iniciar.",
  "Remove backup history older than how many days?":
    "Remover o histórico de backup com mais de quantos dias?",
  "Backup destination opened": "Destino do backup aberto",
  "No extra details.": "Sem detalhes adicionais.",
  "Backup pre-check": "Pré-check do backup",
  "Term generated": "Termo gerado",
  "Term printed": "Termo impresso",
  Backups: "Backups",
  Search: "Pesquisar",
  "Failed to load workstation history":
    "Falha ao carregar o histórico da workstation",
  "An unexpected error occurred.": "Ocorreu um erro inesperado.",
  "Reload Page": "Recarregar página",
  "Page Not Found": "Página não encontrada",
  "Go Home": "Ir para o início",
  "Sorry, the page you are looking for doesn't exist.":
    "A página que você procura não existe.",
  "It may have been moved or deleted.": "Ela pode ter sido movida ou excluída.",
  "Go to Dashboard": "Ir para o Painel",
  Started: "Iniciado",
  "Installing update...": "Instalando atualização...",
  "Update installed. Restart WMT to finish.":
    "Atualização instalada. Reinicie o WMT para concluir.",
  "Update now": "Atualizar agora",
  "Current version:": "Versão atual:",
  Article: "Artigo",
  Progress: "Progresso",
  "Terms print frame": "Área de impressão dos termos",
  "Unknown error": "Erro desconhecido",
  "Authentication failed": "Falha na autenticação",
  "Invalid credentials": "Credenciais inválidas",
  "User is not active": "O usuário não está ativo",
  "Missing session cookie": "Cookie de sessão ausente",
  "Invalid session": "Sessão inválida",
  "Session expired": "Sessão expirada",
  "Invalid CSRF token": "Token CSRF inválido",
  "SSO is disabled": "O SSO está desabilitado",
  "User is not authorized for WMT": "Usuário não autorizado no WMT",
  "Host is empty.": "O host está vazio.",
  "Path is empty.": "O caminho está vazio.",
  User: "Usuário",
  "AD Users": "Usuários do AD",
  "Host Performance": "Desempenho do host",
  "Machine Replacement": "Troca de máquina",
  "Example: D:\\BackupWMT or leave empty to use the default":
    "Exemplo: D:\\BackupWMT ou deixe vazio para usar o padrão",
  "Update timeout (min)": "Timeout de atualização (min)",
  "SCCM timeout (s)": "Timeout do SCCM (s)",
  "SCCM polling (s)": "Consulta do SCCM (s)",
  queued: "na fila",
  running: "em execução",
  completed: "concluído",
  failed: "falhou",
  canceled: "cancelado",
  active: "ativo",
  inactive: "inativo",
  locked: "bloqueado",
};

const ptToEnOverrides: Record<string, string> = {
  Painel: "Dashboard",
  Tarefas: "Tasks",
  "Histórico WK": "WK History",
  Termos: "Terms",
  Usuários: "Users",
  "Configurações de administrador": "Admin Settings",
  Configurações: "Settings",
  "Central de comando": "Command Center",
  "Logado como": "Logged in as",
  Sair: "Logout",
  Atualizar: "Refresh",
  Salvar: "Save",
  "Salvando...": "Saving...",
  "Configurações operacionais do WMT.": "Operational settings for WMT.",
  "Idioma da interface": "Interface language",
  "Escolha o idioma usado pelo WMT nesta workstation.":
    "Choose the language used by WMT on this workstation.",
  Idioma: "Language",
  Inglês: "English",
  Ingles: "English",
  Português: "Portuguese",
  Portugues: "Portuguese",
  "Timeouts e polling": "Timeouts and polling",
  "Scripts habilitados": "Enabled scripts",
  "Caminho padrão de destino": "Default destination path",
  "Aliases de ações remotas": "Remote action aliases",
  "JSON simples. Ex.:": "Simple JSON. Example:",
  "Configurações salvas": "Settings saved",
  "Falha ao salvar configurações": "Failed to save settings",
  "Verifique os campos informados.": "Check the fields and try again.",
  "Log de diagnóstico": "Diagnostic log",
  "Pacote visual de diagnóstico": "Visual diagnostic package",
  "Inventário detalhado": "Detailed inventory",
  Limpeza: "Cleanup",
  Sistema: "System",
  "Discos e BitLocker": "Disks and BitLocker",
  "Softwares instalados": "Installed software",
  "Ações remotas": "Remote Actions",
  "Ações rápidas": "Quick Actions",
  "Gerando diagnóstico visual...": "Generating visual diagnostic...",
  "Consultando...": "Consulting...",
  "Nenhum disco retornado.": "No disk returned.",
  "Nenhum software instalado retornado.": "No installed software returned.",
  "Senha atual": "Current Password",
  "Nova senha": "New Password",
  "Confirmar senha": "Confirm Password",
  "Informe a senha atual": "Enter current password",
  "Informe a nova senha": "Enter new password",
  "Confirme a nova senha": "Confirm new password",
  "Pesquisar usuários": "Search Users",
  "Pesquisar por usuário ou email...": "Search by username or email...",
  Perfil: "Role",
  Senha: "Password",
  "Informe o usuário": "Enter username",
  "Informe o email": "Enter email",
  "Informe a senha": "Enter password",
  Destino: "Destination",
  Histórico: "History",
  Início: "Start",
  Origem: "Source",
  "Tarefas remotas": "Remote Tasks",
  Ativas: "Active",
  Concluídas: "Completed",
  Falhas: "Failed",
  Canceladas: "Canceled",
  "Histórico da workstation": "Workstation History",
  Diagnósticos: "Diagnostics",
  Erros: "Errors",
  "Usuário atual": "Current user",
  "Endereço IP": "IP Address",
  "Endereço MAC": "MAC Address",
  "Último boot": "Last Boot",
  Fabricante: "Manufacturer",
  Modelo: "Model",
  "Número de série": "Serial Number",
  "Sistema operacional": "Operating System",
  Processador: "Processor",
  Atualizações: "Updates",
  "Host selecionado:": "Selected host:",
  "Informe uma workstation primeiro.": "Enter a workstation first.",
  "DOCX gerado e pronto": "DOCX generated and ready",
  "Nome completo do funcionário": "Employee full name",
  Nome: "Name",
  "A prévia de impressão ainda não está pronta.":
    "Print preview is not ready yet.",
  "Acesso não autorizado": "Unauthorized access",
  "Sua conta não possui a permissão necessária para acessar esta área.":
    "Your account does not have permission to access this area.",
  "Conectando com sua sessão do Active Directory":
    "Connecting with your Active Directory session",
  "Detectando usuário Windows e permissões no AD...":
    "Detecting Windows user and AD permissions...",
  Usuário: "Username",
  Entrar: "Sign in",
  "Entrar com Active Directory": "Sign in with Active Directory",
};

const ptToEnInterface: Record<string, string> = {
  "Abrir central de backups": "Open backup center",
  "Abrir menu principal": "Open main menu",
  "Abrir no web": "Open on the web",
  Ação: "Action",
  Ações: "Actions",
  "Ação necessária": "Action required",
  "Acesso rápido aos equipamentos vistos nas operações.":
    "Quick access to devices seen during operations.",
  "Ações e atualizações": "Actions and updates",
  "Ajuste o filtro ou execute uma ação no Monitor.":
    "Adjust the filter or run an action from Monitor.",
  "Ambiente estável": "Environment stable",
  "Analise hardware, armazenamento, SCCM e inventário.":
    "Review hardware, storage, SCCM, and inventory.",
  "As ações realizadas no WMT serão registradas neste espaço.":
    "Actions performed in WMT will be recorded here.",
  "As métricas aparecerão após as primeiras operações registradas.":
    "Metrics will appear after the first recorded operations.",
  "As próximas tarefas ativas aparecerão aqui automaticamente.":
    "Upcoming active tasks will appear here automatically.",
  Atenção: "Attention",
  "Ativar modo manutenção": "Enable maintenance mode",
  Atualização: "Update",
  "Atualização automática em 10s": "Automatic refresh in 10s",
  "Backend incompatível": "Incompatible backend",
  "Backend indisponível": "Backend unavailable",
  "Busca rápida": "Quick search",
  "Buscar por host, ID ou ação": "Search by host, ID, or action",
  "Carregando dados do usuário": "Loading user data",
  "Carregar usuários": "Load users",
  "Carregue os usuários da workstation de origem para continuar.":
    "Load the users from the source workstation to continue.",
  "Central de operações do WMT. Monitore a saúde do ambiente, execute rotinas e resolva pendências em um único lugar.":
    "WMT operations center. Monitor environment health, run routines, and resolve pending items in one place.",
  Chamado: "Ticket",
  "Comece informando as duas workstations. O WMT usa sua sessão Windows/AD para acessar os caminhos.":
    "Start by entering both workstations. WMT uses your Windows/AD session to access the paths.",
  "Comece localizando um equipamento": "Start by finding a device",
  "Como encontrar este equipamento": "How to find this device",
  "Comparação de softwares concluída": "Software comparison completed",
  "Comparar origem e destino": "Compare source and destination",
  "Comparativo de usuários do AD": "AD user comparison",
  "Compartilhamentos temporários disponíveis agora.":
    "Temporary shares currently available.",
  Concluídas: "Completed",
  Concluído: "Completed",
  Conclusão: "Completion",
  "Conectividade e espaço": "Connectivity and space",
  "Confirmação das pastas": "Folder confirmation",
  "Consulta e resultado do equipamento": "Device lookup and result",
  Conta: "Account",
  "Conta habilitada": "Account enabled",
  Cópia: "Copy",
  "Cópia concluída": "Copy completed",
  "Copiar resumo para chamado": "Copy summary to ticket",
  "Copiar resumo para ticket": "Copy summary to ticket",
  "Dados do diretorio": "Directory data",
  "Destino da migração": "Migration destination",
  "Destino dos perfis": "Profile destination",
  Diagnóstico: "Diagnostics",
  "Disco (total)": "Disk (total)",
  Disponível: "Available",
  Duração: "Duration",
  "Duração máxima": "Maximum duration",
  "Em execução": "Running",
  "Endereço IP": "IP address",
  "Endereço MAC": "MAC address",
  "Entradas rápidas para as rotinas mais usadas.":
    "Quick access to the most frequently used routines.",
  Equipamento: "Device",
  equipamento: "device",
  "Equipamento conhecido": "Known device",
  "Equipamento indisponível": "Device unavailable",
  "Erro desconhecido": "Unknown error",
  "Escolha entre migração de perfis ou cópia de uma pasta específica.":
    "Choose between profile migration or copying a specific folder.",
  Escritório: "Office",
  "Estação de trabalho": "Workstation",
  "Estações protegidas, responsável e tempo restante.":
    "Protected workstations, owner, and remaining time.",
  "Estado da conta": "Account status",
  Exclusões: "Exclusions",
  "Executar validação rápida": "Run quick validation",
  "Faça pre-check ou simulação antes de iniciar o backup.":
    "Run a pre-check or simulation before starting the backup.",
  "Falhas de senha": "Password failures",
  "Falhas recentes para resolver sem precisar procurar em cada tela.":
    "Recent failures to resolve without searching each page.",
  "Fechar notificação": "Close notification",
  "Excluir falha da lista": "Remove failure from list",
  "Fila ativa e histórico das ações remotas.":
    "Active queue and remote action history.",
  "Fluxo guiado por etapas para migrar perfis ou copiar uma pasta customizada.":
    "Step-by-step flow to migrate profiles or copy a custom folder.",
  "Gerar novamente": "Generate again",
  "Gerar PDF": "Generate PDF",
  "Gerar termo": "Generate document",
  "Gere o termo primeiro": "Generate the document first",
  Histórico: "History",
  "Histórico de login": "Login history",
  "Histórico operacional por WK: backups, ações remotas, diagnósticos e termos.":
    "Operational history by workstation: backups, remote actions, diagnostics, and documents.",
  "Identidade e rede": "Identity and network",
  "Identificar perfis": "Identify profiles",
  "Impressora indisponível": "Printer unavailable",
  Imprimir: "Print",
  "Imprimir conteúdo editado": "Print edited content",
  "Imprimir editado": "Print edited",
  indisponível: "unavailable",
  "Informações organizacionais e meios de contato do colaborador.":
    "Employee organization and contact information.",
  "Informe as workstations": "Enter the workstations",
  "Informe uma workstation.": "Enter a workstation.",
  "Iniciar cópia": "Start copy",
  "Iniciar nova cópia": "Start a new copy",
  "Instalar atualizações": "Install updates",
  "Instalar no destino": "Install on destination",
  "Inventário detalhado": "Detailed inventory",
  "Ir para o conteúdo": "Skip to content",
  "Limpeza rápida": "Quick cleanup",
  "Localizar equipamento ou usuário": "Find device or user",
  Máquinas: "Machines",
  Matrícula: "Employee ID",
  Memória: "Memory",
  "Migração concluída": "Migration completed",
  "Migração não concluída": "Migration not completed",
  "Modo Manutenção": "Maintenance mode",
  "Modo manutenção ativado": "Maintenance mode enabled",
  "Modo manutenção removido": "Maintenance mode disabled",
  "Modos de manutenção ativos": "Active maintenance modes",
  "Motivo da manutenção": "Maintenance reason",
  "Não consultado": "Not checked",
  "Não detectado": "Not detected",
  "Não informada": "Not provided",
  "Não informado": "Not provided",
  "Navegação principal": "Main navigation",
  "Nenhum backup criado ainda.": "No backups have been created yet.",
  "Nenhum diagnóstico registrado.": "No diagnostics recorded.",
  "Nenhum erro recente encontrado.": "No recent errors found.",
  "Nenhum evento encontrado para esta WK.":
    "No events found for this workstation.",
  "Nenhum host recente": "No recent hosts",
  "Nenhum modo de manutenção ativo agora.":
    "No active maintenance modes right now.",
  "Nenhum perfil selecionado.": "No profiles selected.",
  "Nenhum Temp C share ativo agora.": "No active Temp C shares right now.",
  "Nenhum termo registrado.": "No documents recorded.",
  "Nenhum usuário encontrado": "No users found",
  "Nenhuma ação remota relacionada.": "No related remote actions.",
  "Nenhuma atividade recente": "No recent activity",
  "Nenhuma operação em execução": "No operations running",
  "Nenhuma operação registrada": "No operations recorded",
  "Nenhuma tarefa encontrada.": "No tasks found.",
  "Nome, login, e-mail ou matrícula": "Name, login, email, or employee ID",
  "Nomes dos perfis": "Profile names",
  "Número de série": "Serial number",
  "Operação em andamento": "Operation in progress",
  "Operações que estão ativas ou abertas neste momento.":
    "Operations that are active or open right now.",
  "Operações recentes": "Recent operations",
  "Origem e destino": "Source and destination",
  "Origem, destino e colaborador": "Source, destination, and employee",
  "Padrões excluídos": "Excluded patterns",
  Pasta: "Folder",
  "Pasta customizada": "Custom folder",
  "Pasta de destino": "Destination folder",
  "Pasta de origem": "Source folder",
  "Pasta de destino selecionada": "Destination folder selected",
  "Pasta salva removida": "Saved folder removed",
  Perfis: "Profiles",
  "Perfis carregados": "Loaded profiles",
  "Perfis de usuário": "User profiles",
  "Perfis ou pasta customizada": "Profiles or custom folder",
  "Perfis selecionados": "Selected profiles",
  "Pesquisa de usuários": "User search",
  "Pesquisando usuários e equipamentos...": "Searching users and devices...",
  Pesquisar: "Search",
  "Pesquisar aplicativo ou versão": "Search application or version",
  "Pesquisar este equipamento": "Search this device",
  "Precisa de atenção": "Needs attention",
  "Progresso e histórico": "Progress and history",
  "Próxima etapa": "Next step",
  Próximo: "Next",
  Rede: "Network",
  "Registrado no histórico": "Recorded in history",
  "Registrar no chamado": "Add to ticket",
  "Relatório da troca de máquina": "Machine replacement report",
  "Relatório final da migração": "Final migration report",
  Revisão: "Review",
  "Revisão e execução": "Review and execution",
  "Saúde operacional": "Operational health",
  "Seleção de perfis": "Profile selection",
  "Selecionar dados da migração": "Select migration data",
  "Selecionar pasta": "Select folder",
  "Selecionar pasta de destino": "Select destination folder",
  "Selecionar pasta de origem": "Select source folder",
  "Selecione usuários": "Select users",
  "Sem dados históricos": "No historical data",
  Senha: "Password",
  "Sessão AD detectada": "AD session detected",
  "Sessão local": "Local session",
  "Técnico responsável": "Responsible technician",
  Termos: "Documents",
  "Troca de máquina": "Machine replacement",
  "Última inicialização": "Last boot",
  "Últimas ações:": "Latest actions:",
  "Último logon": "Last logon",
  "Usuário não encontrado": "User not found",
  "Usuários encontrados": "Users found",
  "Usuários protegidos:": "Protected users:",
  Validação: "Validation",
  "Validação rápida": "Quick validation",
  "Validar e gerar termo": "Validate and generate document",
  "Ver histórico": "View history",
  "Verifique a conta": "Check the account",
  Versão: "Version",
  "Versão:": "Version:",
  "WKS de destino": "Destination workstation",
  "WKS de origem": "Source workstation",
  "Workstation de destino": "Destination workstation",
  "Workstation de origem": "Source workstation",
};

const ptToEnRemaining: Record<string, string> = {
  "- Sem ações recentes registradas para este host.":
    "- No recent actions recorded for this host.",
  "• Proteção:": "• Protection:",
  "A prévia de limpeza é calculada ao clicar em Limpeza.":
    "The cleanup preview is calculated when you click Cleanup.",
  "Acesse ferramentas remotas e registre ações no histórico.":
    "Access remote tools and record actions in history.",
  "Ao remover o modo, as tarefas e arquivos serão excluídos e as políticas de logon anteriores serão restauradas automaticamente.":
    "When the mode is disabled, its tasks and files will be deleted and the previous logon policies will be restored automatically.",
  "aplicativo(s) que exigem instalação ou atualização.":
    "application(s) requiring installation or an update.",
  "Atualizações concluídas ou sem pendências para este host.":
    "Updates completed or no pending updates for this host.",
  "Automática a cada 1,5s": "Automatic every 1.5s",
  "BitLocker não retornou volumes.": "BitLocker returned no volumes.",
  "Clique em “Identificar perfis” para consultar":
    "Click “Identify profiles” to check",
  "Clique em Inventário detalhado para consultar programas instalados.":
    "Click Detailed inventory to check installed programs.",
  "Clique no documento para editar antes de imprimir.":
    "Click the document to edit it before printing.",
  "Coletando o inventário da estação...": "Collecting workstation inventory...",
  "Compare o usuario pesquisado com uma referencia para ver acessos e licencas diferentes.":
    "Compare the searched user with a reference to view differences in access and licenses.",
  "Consultando conectividade, acesso remoto e disco...":
    "Checking connectivity, remote access, and disk...",
  "Consulte bloqueio, senha, último logon e situação no AD.":
    "Check lockout, password, last logon, and AD status.",
  "Copia Desktop, Documents, Downloads, Favorites, Pictures e Videos dos perfis selecionados.":
    "Copies Desktop, Documents, Downloads, Favorites, Pictures, and Videos from the selected profiles.",
  "Copia uma pasta absoluta da origem para uma pasta absoluta no destino.":
    "Copies an absolute folder from the source to an absolute folder on the destination.",
  "CPU, Memória, Disco, Rede e Temperatura (quando disponível)":
    "CPU, Memory, Disk, Network, and Temperature (when available)",
  origem: "source",
  destino: "destination",
  "Disco não retornado no lookup.": "Disk was not returned by the lookup.",
  "DOCX da rede": "Network DOCX",
  "DOCX inválido": "Invalid DOCX",
  "Encontre um colaborador, valide sua conta e reúna as informações necessárias para o atendimento.":
    "Find an employee, validate the account, and gather the information required for support.",
  "Equipamentos consultados e usados em operações aparecerão aqui.":
    "Devices checked and used in operations will appear here.",
  "Erro desconhecido ao coletar performance.":
    "Unknown error while collecting performance data.",
  "Erro desconhecido ao consultar histórico do host.":
    "Unknown error while loading host history.",
  "Erro desconhecido ao consultar o Software Center.":
    "Unknown error while checking Software Center.",
  "Erro desconhecido ao consultar update job.":
    "Unknown error while checking the update job.",
  "Erro desconhecido ao executar a ação.":
    "Unknown error while running the action.",
  "Erro desconhecido ao gerar diagnóstico.":
    "Unknown error while generating diagnostics.",
  "Erro desconhecido ao iniciar atualizações.":
    "Unknown error while starting updates.",
  "Erro desconhecido na busca.": "Unknown search error.",
  "Esses dados podem ajudar a identificar o equipamento mesmo sem comunicação remota.":
    "This data can help identify the device even without remote communication.",
  "Execute rotinas de suporte no equipamento selecionado e acompanhe o resultado.":
    "Run support routines on the selected device and track the result.",
  "Falha ao ativar o modo manutenção": "Failed to enable maintenance mode",
  "Falha ao atualizar o job.": "Failed to update the job.",
  "Falha ao autenticar": "Authentication failed",
  "Falha ao comparar softwares": "Failed to compare software",
  "Falha ao comparar usuario": "Failed to compare user",
  "Falha ao consultar usuario": "Failed to look up user",
  "Falha ao gerar relatório": "Failed to generate report",
  "Falha ao gerar termo": "Failed to generate document",
  "Falha ao identificar perfis": "Failed to identify profiles",
  "Falha ao iniciar a cópia": "Failed to start copy",
  "Falha ao remover o modo manutenção": "Failed to disable maintenance mode",
  "Falha ao renderizar o termo": "Failed to render document",
  "Falha na limpeza rápida": "Quick cleanup failed",
  "Falha na validação": "Validation failed",
  "Grupos de acesso retornados pelo AD, excluindo sinais de licenca.":
    "Access groups returned by AD, excluding license signals.",
  "Histórico indisponível para o resumo completo.":
    "History is unavailable for the full summary.",
  "Host é obrigatório.": "Host is required.",
  "Impressora identificada pelo range de rede":
    "Printer identified by network range",
  "Inclui dados copiados, resultado do backup e":
    "Includes copied data, backup result, and",
  "Informe um hostname ou IP para pesquisar.":
    "Enter a hostname or IP address to search.",
  "Informe um usuario de referencia para comparar acessos.":
    "Enter a reference user to compare access.",
  "Informe usuário e senha.": "Enter username and password.",
  "Início:": "Started:",
  "Job de migração iniciado": "Migration job started",
  "Lendo informações do Active Directory...":
    "Reading Active Directory information...",
  "Limpeza pendente • clique em Remover manutenção":
    "Cleanup pending • click Disable maintenance",
  "Limpeza rápida solicitada": "Quick cleanup requested",
  "Localize uma estação ou impressora, confirme seu estado e execute o atendimento sem trocar de tela.":
    "Find a workstation or printer, confirm its status, and perform support without switching pages.",
  "Média dos suprimentos": "Average supply level",
  "Montando relatório e convertendo para PDF...":
    "Building report and converting it to PDF...",
  "Não altera senha": "Does not change password",
  "Não foi possível abrir a configuração web":
    "Could not open the web configuration",
  "Não foi possível abrir a pasta": "Could not open the folder",
  "Não foi possível abrir a pasta.": "Could not open the folder.",
  "Não foi possível abrir o Temp C share": "Could not open the Temp C share",
  "Não foi possível cancelar": "Could not cancel",
  "Não foi possível carregar o Dashboard": "Could not load Dashboard",
  "Não foi possível concluir a consulta": "Could not complete the lookup",
  "Não foi possível consultar o Active Directory":
    "Could not query Active Directory",
  "Não foi possível copiar o resumo": "Could not copy the summary",
  "Não foi possível copiar o resumo para o ticket":
    "Could not copy the summary to the ticket",
  "Não foi possível remover o Temp C share":
    "Could not remove the Temp C share",
  "Não há falhas abertas ou operações aguardando execução.":
    "There are no open failures or operations waiting to run.",
  'Nenhum aplicativo encontrado para "': 'No application found for "',
  "Nenhum backup relacionado.": "No related backups.",
  "Nenhum sinal de licença Office/M365 encontrado no AD.":
    "No Office/M365 license signal found in AD.",
  "Nenhum suprimento retornado pelo SNMP.": "No supplies returned by SNMP.",
  "Nenhum usuário ou equipamento conhecido foi encontrado.":
    "No known user or device was found.",
  "Nenhuma atualização pendente listada para este host.":
    "No pending updates listed for this host.",
  "Nenhuma estação registrada para este usuário no histórico do WMT.":
    "No workstation recorded for this user in WMT history.",
  "Nenhuma liberação encontrada para este usuário.":
    "No release found for this user.",
  "Nenhuma nesta sessão": "None in this session",
  "Nenhuma temperatura retornada (WMI/ACPI). Dependendo do modelo, pode não existir.":
    "No temperature returned (WMI/ACPI). It may not be available on this model.",
  "O WMT aplicará uma lock screen de manutenção no Windows e bloqueará o login dos colaboradores identificados. O usuário administrativo que ativar o modo continuará disponível para o suporte via RDP.":
    "WMT will apply a maintenance lock screen in Windows and block logon for the identified employees. The administrator who enabled the mode will remain available for support through RDP.",
  "O WMT carregará o mesmo termo de responsabilidade e aceitação configurado no módulo Terms.":
    "WMT will load the same responsibility and acceptance document configured in the Terms module.",
  "O WMT manteve a classificação como impressora, mas não conseguiu obter dados de rede ou SNMP.":
    "WMT kept the printer classification but could not retrieve network or SNMP data.",
  "Operações frequentes para conexão e suporte.":
    "Frequent connection and support operations.",
  "Os softwares das duas máquinas são equivalentes.":
    "The software on both machines is equivalent.",
  para: "to",
  "Pasta aberta": "Folder opened",
  "pasta(s)": "folder(s)",
  "pendente(s)": "pending",
  "Pesquisar “": "Search “",
  "Pesquise uma workstation para carregar o histórico.":
    "Search for a workstation to load its history.",
  "Preparando o resumo do diagnóstico...": "Preparing diagnostics summary...",
  "Prévia rápida do lookup": "Quick lookup preview",
  "Procure por hostname, usuário ou número de patrimônio.":
    "Search by hostname, user, or asset number.",
  "Proteção de manutenção não confirmada":
    "Maintenance protection not confirmed",
  "Quando uma rotina for executada, o resultado aparecerá aqui.":
    "When a routine runs, its result will appear here.",
  "Relatório PDF gerado": "PDF report generated",
  "Remover manutenção": "Disable maintenance",
  "Resumo copiado para o chamado": "Summary copied to the ticket",
  "Resumo copiado para o ticket": "Summary copied to the ticket",
  "Resumo do equipamento": "Device summary",
  "Revise grupos, liberações e sinais de licença Microsoft 365.":
    "Review groups, releases, and Microsoft 365 license signals.",
  "Revise os caminhos antes de seguir para a execução.":
    "Review the paths before proceeding.",
  "Selecione o colaborador correto para abrir o perfil completo.":
    "Select the correct employee to open the full profile.",
  "Sem dados de interfaces.": "No interface data.",
  "Sem dados de volumes.": "No volume data.",
  "Sem falhas recentes em operações acompanhadas.":
    "No recent failures in tracked operations.",
  "Sem permissão para executar ações remotas neste host.":
    "You do not have permission to run remote actions on this host.",
  "Sem permissão para executar limpeza rápida.":
    "You do not have permission to run quick cleanup.",
  "Sem permissão para iniciar updates neste host.":
    "You do not have permission to start updates on this host.",
  "Sem varredura profunda das pastas; conectividade, acesso, perfis e disco continuam sendo verificados.":
    "Without a deep folder scan; connectivity, access, profiles, and disk are still checked.",
  "Senha alterada": "Password changed",
  "Senha nunca expira": "Password never expires",
  Serviço: "Service",
  "Sinais de autenticação disponíveis no AD sem consulta direta ao Event Viewer.":
    "Authentication signals available in AD without querying Event Viewer directly.",
  "Software Center, cliente SCCM e atualizações do equipamento.":
    "Software Center, SCCM client, and device updates.",
  "Softwares não são carregados na coleta rápida.":
    "Software is not loaded during quick collection.",
  "tarefa(s)": "task(s)",
  "tarefa(s) filtradas.": "filtered task(s).",
  "Termo da rede carregado e pronto para edição":
    "Network document loaded and ready for editing",
  "Última estação vista pelo WMT": "Last workstation seen by WMT",
  "Última falha de senha": "Last password failure",
  "Últimas execuções de backup, tarefas remotas e atualizações, em uma única fila.":
    "Latest backup runs, remote tasks, and updates in a single queue.",
  "Últimas informações do Active Directory":
    "Latest Active Directory information",
  "Último logon conhecido": "Last known logon",
  "Último logon no DC consultado": "Last logon on the queried DC",
  "Uma migração guiada, com validações rápidas e acompanhamento visível do início ao fim.":
    "A guided migration with quick validations and visible progress from start to finish.",
  "Use a busca acima com hostname, endereço IP, número de série, usuário ou matrícula.":
    "Use the search above with a hostname, IP address, serial number, user, or employee ID.",
  "Usuário, e-mail, matrícula, WKS, IP ou serial":
    "User, email, employee ID, workstation, IP, or serial",
  "Usuário:": "User:",
  "Usuários:": "Users:",
  "Validando origem e destino em paralelo":
    "Validating source and destination in parallel",
  "Veja conectividade, usuário atual e informações do Windows.":
    "View connectivity, current user, and Windows information.",
  "Verificando a comunicação pela rede...": "Checking network communication...",
  "Você pode usar nome, login de rede, e-mail, UPN ou número de matrícula.":
    "You can use name, network login, email, UPN, or employee ID.",
  "Volume e resultado das operações nos últimos sete dias.":
    "Operation volume and results over the last seven days.",
  "Windows SSO indisponível": "Windows SSO unavailable",
  "Sistema conectado": "System connected",
  "Backups hoje": "Backups today",
  "Bom dia": "Good morning",
  "Boa tarde": "Good afternoon",
  "Boa noite": "Good evening",
  ", operador": ", operator",
  "Tentar novamente": "Try again",
  Instalado: "Installed",
  "Backup em andamento": "Backup in progress",
  "Host não informado": "Host not provided",
  "Destino aberto": "Destination opened",
  "Ação remota": "Remote action",
  "Termo DOCX": "DOCX document",
  "Diagnóstico iniciado": "Diagnostics started",
  "Diagnóstico registrado": "Diagnostics recorded",
  Impressora: "Printer",
  impressora: "printer",
  IMPRESSORA: "PRINTER",
  "Pesquisa no Active Directory": "Active Directory search",
  "Busca universal": "Universal search",
  "Sessão expirada. Faça login novamente.": "Session expired. Sign in again.",
  "A configuração web da impressora aceita somente HTTP.":
    "The printer web configuration only supports HTTP.",
  "Esta ação precisa ser aberta pelo app desktop WMT.":
    "This action must be opened by the WMT desktop app.",
  Nao: "No",
  Nenhum: "None",
  Nenhuma: "None",
  "Usuário do AD": "AD user",
  "Usuário do Active Directory": "Active Directory user",
  "Faltando no usuario pesquisado": "Missing from searched user",
  "Extra no usuario pesquisado": "Extra on searched user",
  "Comparar usuarios": "Compare users",
  "Nao foi possivel copiar o comparativo": "Could not copy the comparison",
  "Usuario de referencia": "Reference user",
  "Usuario pesquisado": "Searched user",
  "Usuario nao encontrado no AD": "User not found in AD",
  "Usuario de referencia nao encontrado.": "Reference user not found.",
  "Perfil e contato": "Profile and contact",
  "Selecione uma pasta dentro do compartilhamento temporário aberto pelo WMT.":
    "Select a folder inside the temporary share opened by WMT.",
  "Informe o destino para visualizar o caminho.":
    "Enter the destination to preview the path.",
  "Nenhum log de simulação retornado.": "No simulation log returned.",
  "Nenhum backup ativo agora.": "No active backups right now.",
  Detalhes: "Details",
  Resumo: "Summary",
  "Sem resumo disponível.": "No summary available.",
  "Nenhum log disponível para este job.": "No log available for this job.",
  Copiado: "Copied",
  "Tarefa remota em andamento": "Remote task in progress",
  "Ação remota registrada": "Remote action recorded",
  "O job terminou com falha.": "The job failed.",
  "versao da origem": "source version",
  "Não instalado": "Not installed",
  "Host offline ou indisponível.": "Host offline or unavailable.",
  "Objeto encontrado no AD.": "Object found in AD.",
  "Sem dados do AD.": "No AD data.",
  Disco: "Disk",
  "O equipamento está desligado ou não pode ser alcançado pela rede.":
    "The device is powered off or cannot be reached over the network.",
  "A impressora pertence ao range reservado":
    "The printer belongs to the reserved network range",
  "Modelo não retornado pelo SNMP": "Model not returned by SNMP",
  "O equipamento respondeu na rede, mas os detalhes SNMP não estão disponíveis.":
    "The device responded on the network, but SNMP details are unavailable.",
  "Sem nível": "No level",
  "Consultando softwares instalados...": "Checking installed software...",
  "Calculando e executando limpeza...": "Calculating and running cleanup...",
  "Diagnóstico não concluiu dentro do tempo esperado.":
    "Diagnostics did not finish within the expected time.",
  "Atualizações do Software Center iniciadas.":
    "Software Center updates started.",
  "Ação remota enviada para execução.": "Remote action submitted.",
  "Ação remota falhou.": "Remote action failed.",
  Consultando: "Checking",
  "usuário não identificado": "unidentified user",
  usuário: "user",
  "Sistema operacional não identificado": "Operating system not identified",
  "Disco local C:": "Local disk C:",
  "Monitorando progresso automaticamente a cada 10s em":
    "Automatically monitoring progress every 10s on",
  "Motivo não informado": "Reason not provided",
  "perfil(is) -": "profile(s) -",
  "PowerShell nao encontrado neste ambiente.":
    "PowerShell was not found in this environment.",
  "Falha ao executar diagnostico.": "Failed to run diagnostics.",
  "Falha ao coletar performance.": "Failed to collect performance data.",
  "Manifesto de update encontrado.": "Update manifest found.",
  "Manifesto de update nao encontrado.": "Update manifest not found.",
  "Backups estão desabilitados nas configurações do WMT.":
    "Backups are disabled in WMT settings.",
  "Scripts do Software Center estão desabilitados nas configurações do WMT.":
    "Software Center scripts are disabled in WMT settings.",
  "Ações remotas estão desabilitadas nas configurações do WMT.":
    "Remote actions are disabled in WMT settings.",
  "Falha ao consultar Software Center.": "Failed to check Software Center.",
  "Software Center nao retornou dados.": "Software Center returned no data.",
  "Falha ao consultar shares temporarias.": "Failed to query temporary shares.",
  "Falha ao iniciar updates.": "Failed to start updates.",
  "Falha ao monitorar updates.": "Failed to monitor updates.",
  "Update adicionado à fila.": "Update added to the queue.",
  "Informe o chamado da manutenção": "Enter the maintenance ticket",
  "Informe o motivo da manutenção": "Enter the maintenance reason",
  "Não foi possível identificar o usuário Windows desta estação":
    "Could not identify the Windows user on this workstation",
  "PowerShell não encontrado para consultar usuário remoto":
    "PowerShell was not found to query the remote user",
};

const ptToEn: Record<string, string> = {
  ...Object.fromEntries(
    Object.entries(enToPt).map(([english, portuguese]) => [portuguese, english])
  ),
  ...ptToEnInterface,
  ...ptToEnRemaining,
  ...ptToEnOverrides,
};

const enToPtPatterns: Array<[RegExp, (...groups: string[]) => string]> = [
  [
    /^Delete (.+)\? This cannot be undone\.$/,
    target => `Excluir ${target}? Esta ação não pode ser desfeita.`,
  ],
  [
    /^DOCX ready\. Unused placeholders: (.+)$/,
    placeholders => `DOCX pronto. Placeholders não utilizados: ${placeholders}`,
  ],
  [
    /^Update (.+) is available$/,
    version => `A atualização ${version} está disponível`,
  ],
  [
    /^WMT (.+) is available$/,
    version => `A versão ${version} do WMT está disponível`,
  ],
  [
    /^Downloading WMT (.+?)( \(.+\))?\.\.\.$/,
    (version, progress = "") => `Baixando WMT ${version}${progress}...`,
  ],
  [/^Update failed: (.+)$/, message => `Falha ao atualizar: ${message}`],
  [/^Current version: (.+)$/, version => `Versão atual: ${version}`],
  [/^Task (.+) completed$/, host => `Tarefa ${host} concluída`],
  [/^Task (.+) failed$/, host => `Tarefa ${host} falhou`],
  [/^Task (.+) canceled$/, host => `Tarefa ${host} cancelada`],
  [/^(.+) completed$/, title => `${title} concluído`],
  [/^(.+) failed$/, title => `${title} falhou`],
  [/^(.+) canceled$/, title => `${title} cancelado`],
  [/^Users \((\d+)\)$/, count => `Usuários (${count})`],
];

const ptToEnPatterns: Array<[RegExp, (...groups: string[]) => string]> = [
  [
    /^O serviço encontrado não é compatível com a API (.+)\.$/,
    version => `The detected service is not compatible with API ${version}.`,
  ],
  [/^\(versão (.+)\)$/, version => `(version ${version})`],
  [/^, (\d+) perfil\(is\)$/, count => `, ${count} profile(s)`],
  [/^Usuários(\d+)$/, count => `Users${count}`],
  [/^Matrícula (.+)$/, value => `Employee ID ${value}`],
  [/^Senha alterada: (.+)$/, value => `Password changed: ${value}`],
  [/^Nao foi possivel copiar (.+)$/, target => `Could not copy ${target}`],
  [/^Usuario pesquisado: (.+)$/, value => `Searched user: ${value}`],
  [
    /^Selecione uma pasta compartilhada em (.+)\.$/,
    host => `Select a shared folder on ${host}.`,
  ],
  [
    /^Informe o computador de (.+) primeiro\.$/,
    kind =>
      `Enter the ${kind === "origem" ? "source" : kind === "destino" ? "destination" : kind} workstation first.`,
  ],
  [
    /^Informe a pasta de (.+) primeiro\.$/,
    kind =>
      `Enter the ${kind === "origem" ? "source" : kind === "destino" ? "destination" : kind} folder first.`,
  ],
  [
    /^(\d+) perfil\(is\) - (.+)$/,
    (count, details) => `${count} profile(s) - ${details}`,
  ],
  [
    /^(\d+) perfil\(is\)(.+)$/,
    (count, details) => `${count} profile(s)${details}`,
  ],
  [
    /^(\d+) operação\(ões\) estão sendo processadas agora\.$/,
    count => `${count} operation(s) are being processed now.`,
  ],
  [/^(\d+) concluída\(s\)$/, count => `${count} completed`],
  [/^Fechar notificação: (.+)$/, title => `Close notification: ${title}`],
  [
    /^Excluir falha da lista: (.+)$/,
    title => `Remove failure from list: ${title}`,
  ],
  [/^Última coleta: (.+)$/, value => `Last collection: ${value}`],
  [/^Erro (.+)$/, error => `Error ${error}`],
  [/^Atualizar para (.+)$/, version => `Update to ${version}`],
  [/^Resumo WMT - (.+)$/, value => `WMT summary - ${value}`],
  [/^Usuário atual: (.+)$/, value => `Current user: ${value}`],
  [/^Disco: (.+)$/, value => `Disk: ${value}`],
  [/^Nao foi possivel abrir (.+)$/, target => `Could not open ${target}`],
  [/^Nao foi possivel (.+)$/, action => `Could not ${action}`],
  [
    /^Abertura local iniciada para (.+)\.$/,
    target => `Local opening started for ${target}.`,
  ],
  [/^(.+) indisponível$/, target => `${target} unavailable`],
  [/^Pesquisar (.+)$/, target => `Search ${target}`],
  [/^Script nao encontrado: (.+)$/, script => `Script not found: ${script}`],
  [
    /^Limite de (\d+) backups simultâneos atingido\.$/,
    limit => `The limit of ${limit} simultaneous backups has been reached.`,
  ],
  [
    /^Limite de (\d+) ações remotas simultâneas atingido\.$/,
    limit =>
      `The limit of ${limit} simultaneous remote actions has been reached.`,
  ],
  [
    /^Limite de (\d+) jobs de atualização simultâneos atingido\.$/,
    limit => `The limit of ${limit} simultaneous update jobs has been reached.`,
  ],
  [
    /^Não foi possível concluir a (.+)\.$/,
    context => `Could not complete ${context}.`,
  ],
  [
    /^Acesso negado ao executar (.+)\. Verifique se a conta do backend tem permissão administrativa no host de destino\.$/,
    context =>
      `Access denied while running ${context}. Verify that the backend account has administrative permission on the destination host.`,
  ],
  [
    /^WinRM\/PowerShell Remoting indisponível para (.+)\. Confirme se o host está online, com WinRM habilitado e liberado no firewall\.$/,
    context =>
      `WinRM/PowerShell Remoting is unavailable for ${context}. Confirm that the host is online and WinRM is enabled and allowed through the firewall.`,
  ],
  [
    /^Host não encontrado para (.+)\. Confira o nome da WKS ou DNS\.$/,
    context =>
      `Host not found for ${context}. Check the workstation name or DNS.`,
  ],
  [
    /^Host offline ou compartilhamento administrativo inacessível para (.+)\. Verifique rede, firewall e admin share\.$/,
    context =>
      `Host offline or administrative share inaccessible for ${context}. Check the network, firewall, and admin share.`,
  ],
  [
    /^SCCM Client não foi encontrado ou não respondeu no host durante (.+)\. Verifique se o cliente SCCM está instalado e saudável\.$/,
    context =>
      `SCCM Client was not found or did not respond during ${context}. Verify that the SCCM client is installed and healthy.`,
  ],
  [
    /^Credencial sem permissão ou inválida para (.+)\. Confira usuário, senha e privilégios locais no host\.$/,
    context =>
      `The credential is invalid or lacks permission for ${context}. Check the username, password, and local privileges on the host.`,
  ],
  [
    /^Admin share bloqueado ou sessão SMB conflitante durante (.+)\. Feche conexões antigas e confirme acesso ao C\$\/ADMIN\$\.$/,
    context =>
      `Admin share blocked or conflicting SMB session during ${context}. Close old connections and confirm access to C$/ADMIN$.`,
  ],
  [
    /^(Bom dia|Boa tarde|Boa noite), operador$/,
    greeting =>
      `${greeting === "Bom dia" ? "Good morning" : greeting === "Boa tarde" ? "Good afternoon" : "Good evening"}, operator`,
  ],
  [
    /^(\d+) remota\(s\), (\d+) update\(s\), (\d+) backup\(s\)$/,
    (remote, updates, backups) =>
      `${remote} remote task(s), ${updates} update(s), ${backups} backup(s)`,
  ],
  [
    /^(\d+) falha\(s\), (\d+) concluído\(s\)$/,
    (failed, completed) => `${failed} failed, ${completed} completed`,
  ],
  [
    /^(\d+) rodando, (\d+) falha\(s\)$/,
    (running, failed) => `${running} running, ${failed} failed`,
  ],
  [/^(\d+) usuário\(s\) ativo\(s\)$/, count => `${count} active user(s)`],
  [/^(\d+) falha\(s\)$/, count => `${count} failure(s)`],
  [/^(\d+) perfil\(is\)$/, count => `${count} profile(s)`],
  [
    /^(\d+) perfil\(is\) encontrado\(s\)$/,
    count => `${count} profile(s) found`,
  ],
  [/^(\d+) update\(s\) pendente\(s\)$/, count => `${count} pending update(s)`],
  [
    /^(\d+) operação\(ões\) falharam e precisam de revisão\.$/,
    count => `${count} operation(s) failed and require review.`,
  ],
  [
    /^O Active Directory não retornou correspondências para “(.+)”\.$/,
    query => `Active Directory returned no matches for “${query}”.`,
  ],
  [
    /^O Active Directory não encontrou correspondência para “(.+)”\.$/,
    query => `Active Directory found no match for “${query}”.`,
  ],
  [/^Updates pendentes: (\d+)$/, count => `Pending updates: ${count}`],
  [/^Update job ativo: (.+)$/, details => `Active update job: ${details}`],
  [/^Update job (.+) concluído\.$/, id => `Update job ${id} completed.`],
  [
    /^Lock screen ativa • (\d+) usuário\(s\) bloqueado\(s\)$/,
    count => `Lock screen active • ${count} blocked user(s)`,
  ],
  [
    /^Tem certeza que deseja renovar o IP de (.+)\? A conexão de rede pode cair por alguns segundos\.$/,
    host =>
      `Are you sure you want to renew the IP address of ${host}? The network connection may drop for a few seconds.`,
  ],
  [
    /^Informe o computador de (origem|destino) primeiro\.$/,
    kind =>
      `Enter the ${kind === "origem" ? "source" : "destination"} workstation first.`,
  ],
  [
    /^Informe a pasta de (origem|destino) primeiro\.$/,
    kind =>
      `Enter the ${kind === "origem" ? "source" : "destination"} folder first.`,
  ],
  [/^Não foi possível (.+)$/, action => `Could not ${action}`],
  [/^Falha ao (.+)$/, action => `Failed to ${action}`],
  [
    /^Erro desconhecido ao (.+)$/,
    action => `Unknown error while trying to ${action}`,
  ],
  [/^Remover (.+)$/, target => `Remove ${target}`],
  [/^Usar (.+)$/, target => `Use ${target}`],
  [/^(.+) copiado$/, target => `${target} copied`],
  [/^Total: (.+)$/, value => `Total: ${value}`],
  [/^Usuários: (.+)$/, value => `Users: ${value}`],
  [/^Início: (.+)$/, value => `Started: ${value}`],
];

export function translateText(text: string, language: DisplayLanguage) {
  const trimmed = text.trim();
  if (!trimmed) return text;
  const translated = language === "pt-BR" ? enToPt[trimmed] : ptToEn[trimmed];
  if (translated) return text.replace(trimmed, translated);
  const patterns = language === "pt-BR" ? enToPtPatterns : ptToEnPatterns;
  for (const [pattern, replacement] of patterns) {
    const match = trimmed.match(pattern);
    if (match) {
      return text.replace(trimmed, replacement(...match.slice(1)));
    }
  }
  return text;
}

const textSources = new WeakMap<Node, string>();
const renderedTexts = new WeakMap<Node, string>();
type TranslatableAttribute = "placeholder" | "title" | "aria-label";
type AttributeState = Partial<
  Record<TranslatableAttribute, { source: string; rendered: string }>
>;
const attributeStates = new WeakMap<HTMLElement, AttributeState>();

function translateDocument(language: DisplayLanguage) {
  const translateAttribute = (
    element: HTMLElement,
    attribute: TranslatableAttribute
  ) => {
    const current = element.getAttribute(attribute);
    if (!current) return;

    const states = attributeStates.get(element) || {};
    const previous = states[attribute];
    const source =
      !previous || current !== previous.rendered ? current : previous.source;
    const rendered = translateText(source, language);
    states[attribute] = { source, rendered };
    attributeStates.set(element, states);
    if (rendered !== current) element.setAttribute(attribute, rendered);
  };

  const translateNode = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE && node.textContent) {
      const parent = node.parentElement;
      if (
        !parent ||
        ["SCRIPT", "STYLE", "TEXTAREA", "CODE", "PRE"].includes(parent.tagName)
      )
        return;
      const current = node.textContent;
      const previousRendered = renderedTexts.get(node);
      const source =
        !textSources.has(node) || current !== previousRendered
          ? current
          : textSources.get(node)!;
      const translated = translateText(source, language);
      textSources.set(node, source);
      renderedTexts.set(node, translated);
      if (translated !== current) node.textContent = translated;
      return;
    }

    if (node instanceof HTMLElement) {
      if (node instanceof HTMLInputElement)
        translateAttribute(node, "placeholder");
      translateAttribute(node, "title");
      translateAttribute(node, "aria-label");
      node.childNodes.forEach(translateNode);
    }
  };

  translateNode(document.body);
  return translateNode;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<DisplayLanguage>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "pt-BR" || stored === "en-US" ? stored : "en-US";
  });

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "pt-BR" || stored === "en-US") {
      return;
    }

    let cancelled = false;
    apiFetch("/api/app-preferences")
      .then(response => (response.ok ? response.json() : null))
      .then((payload: { display_language?: DisplayLanguage } | null) => {
        if (
          !cancelled &&
          (payload?.display_language === "pt-BR" ||
            payload?.display_language === "en-US")
        ) {
          setLanguageState(payload.display_language);
          localStorage.setItem(STORAGE_KEY, payload.display_language);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    document.documentElement.lang = language === "pt-BR" ? "pt-BR" : "en-US";
    let translateNode: (node: Node) => void = () => undefined;
    const run = () => {
      translateNode = translateDocument(language);
    };
    window.setTimeout(run, 0);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === "characterData") {
          translateNode(record.target);
        } else if (record.type === "attributes") {
          translateNode(record.target);
        } else {
          record.addedNodes.forEach(translateNode);
        }
      }
    });
    observer.observe(document.body, {
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label"],
      subtree: true,
    });
    return () => observer.disconnect();
  }, [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage: next => {
        setLanguageState(next);
        localStorage.setItem(STORAGE_KEY, next);
      },
      t: text => translateText(text, language),
    }),
    [language]
  );

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used inside LanguageProvider");
  }
  return context;
}
