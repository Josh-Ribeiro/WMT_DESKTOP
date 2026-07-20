import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';

export type DisplayLanguage = 'en-US' | 'pt-BR';

interface LanguageContextValue {
  language: DisplayLanguage;
  setLanguage: (language: DisplayLanguage) => void;
  t: (text: string) => string;
}

const STORAGE_KEY = 'wmt_display_language';

const enToPt: Record<string, string> = {
  'Dashboard': 'Painel',
  'Monitor': 'Monitor',
  'Tasks': 'Tarefas',
  'Backup': 'Backup',
  'WK History': 'Histórico WK',
  'Terms': 'Termos',
  'Users': 'Usuários',
  'Admin Settings': 'Configurações de administrador',
  'Settings': 'Configurações',
  'Command Center': 'Central de comando',
  'Logged in as': 'Logado como',
  'Logout': 'Sair',
  'Refresh': 'Atualizar',
  'Save': 'Salvar',
  'Saving...': 'Salvando...',
  'Operational settings for WMT.': 'Configurações operacionais do WMT.',
  'Interface language': 'Idioma da interface',
  'Choose the language used by WMT on this workstation.': 'Escolha o idioma usado pelo WMT nesta workstation.',
  'Language': 'Idioma',
  'English': 'Inglês',
  'Portuguese': 'Português',
  'Timeouts and polling': 'Timeouts e polling',
  'Enabled scripts': 'Scripts habilitados',
  'Default destination path': 'Caminho padrão de destino',
  'Remote action aliases': 'Aliases de ações remotas',
  'Simple JSON. Example:': 'JSON simples. Exemplo:',
  'Settings saved': 'Configurações salvas',
  'Failed to save settings': 'Falha ao salvar configurações',
  'Check the fields and try again.': 'Verifique os campos informados.',
  'Diagnostic log': 'Log de diagnóstico',
  'Visual diagnostic package': 'Pacote visual de diagnóstico',
  'Detailed inventory': 'Inventário detalhado',
  'Cleanup': 'Limpeza',
  'System': 'Sistema',
  'Disks and BitLocker': 'Discos e BitLocker',
  'Installed software': 'Softwares instalados',
  'Software Center': 'Software Center',
  'Remote Actions': 'Ações remotas',
  'Quick Actions': 'Ações rápidas',
  'Generating visual diagnostic...': 'Gerando diagnóstico visual...',
  'Consulting...': 'Consultando...',
  'No disk returned.': 'Nenhum disco retornado.',
  'No installed software returned.': 'Nenhum software instalado retornado.',
  'No user profiles were found on the source workstation.': 'Nenhum perfil de usuário foi encontrado na workstation de origem.',
  'Current Password': 'Senha atual',
  'New Password': 'Nova senha',
  'Confirm Password': 'Confirmar senha',
  'Enter current password': 'Informe a senha atual',
  'Enter new password': 'Informe a nova senha',
  'Confirm new password': 'Confirme a nova senha',
  'Search Users': 'Pesquisar usuários',
  'Search by username or email...': 'Pesquisar por usuário ou email...',
  'Email': 'Email',
  'Role': 'Perfil',
  'Password': 'Senha',
  'Enter username': 'Informe o usuário',
  'Enter email': 'Informe o email',
  'Enter password': 'Informe a senha',
  'Destination': 'Destino',
  'History': 'Histórico',
  'Start': 'Início',
  'Source': 'Origem',
  'Status': 'Status',
  'Host': 'Host',
  'Remote Tasks': 'Tarefas remotas',
  'Total': 'Total',
  'Active': 'Ativas',
  'Completed': 'Concluídas',
  'Failed': 'Falhas',
  'Canceled': 'Canceladas',
  'Workstation History': 'Histórico da workstation',
  'Remote actions': 'Ações remotas',
  'Diagnostics': 'Diagnósticos',
  'Errors': 'Erros',
  'Workstation': 'Workstation',
  'Hostname': 'Hostname',
  'IP Address': 'Endereço IP',
  'MAC Address': 'Endereço MAC',
  'Last Boot': 'Último boot',
  'Manufacturer': 'Fabricante',
  'Model': 'Modelo',
  'Serial Number': 'Número de série',
  'Operating System': 'Sistema operacional',
  'Processor': 'Processador',
  'Updates': 'Atualizações',
  'Selected host:': 'Host selecionado:',
  'Enter a workstation first.': 'Informe uma workstation primeiro.',
  'DOCX generated and ready': 'DOCX gerado e pronto',
  'Employee full name': 'Nome completo do funcionário',
  'Name': 'Nome',
  'Print preview is not ready yet.': 'A prévia de impressão ainda não está pronta.',
  'Account details, access profile and WMT appearance preferences.': 'Detalhes da conta, perfil de acesso e preferências visuais do WMT.',
  'Local account': 'Conta local',
  'Profile': 'Perfil',
  'Current identity used by WMT.': 'Identidade atual usada pelo WMT.',
  'Display name': 'Nome de exibição',
  'Username': 'Usuário',
  'Domain': 'Domínio',
  'Local': 'Local',
  'Not available': 'Não disponível',
  'Permissions': 'Permissões',
  'No explicit permissions loaded.': 'Nenhuma permissão explícita carregada.',
  'Session': 'Sessão',
  'Current authentication state.': 'Estado atual da autenticação.',
  'Authenticated with your Windows account.': 'Autenticado com sua conta Windows.',
  'Authenticated with a local WMT account.': 'Autenticado com uma conta local do WMT.',
  'Access is controlled by your role and available permissions.': 'O acesso é controlado pelo seu perfil e permissões disponíveis.',
  'Appearance': 'Aparência',
  'Choose how WMT should look on this workstation.': 'Escolha como o WMT deve aparecer nesta workstation.',
  'Dark mode': 'Modo escuro',
  'Use a darker interface for low-light environments.': 'Use uma interface mais escura para ambientes com pouca luz.',
  'Accent color': 'Cor de destaque',
  'This changes buttons, selected navigation and focus color.': 'Isto altera botões, navegação selecionada e cor de foco.',
  'Blue': 'Azul',
  'Violet': 'Violeta',
  'Pink': 'Rosa',
  'Emerald': 'Esmeralda',
  'Cyan': 'Ciano',
  'Amber': 'Âmbar',
  'Preview': 'Prévia',
  'Primary action': 'Ação primária',
  'Secondary': 'Secundária',
  'Selected': 'Selecionado',
  'Security': 'Segurança',
  'Password is managed by Active Directory for this session.': 'A senha é gerenciada pelo Active Directory nesta sessão.',
  'Manage your local WMT password.': 'Gerencie sua senha local do WMT.',
  'Windows account security': 'Segurança da conta Windows',
  'Password changes should be done through Windows/Active Directory policies.': 'Alterações de senha devem ser feitas pelas políticas do Windows/Active Directory.',
  'Update Password': 'Atualizar senha',
  'Please fill in all password fields': 'Preencha todos os campos de senha',
  'New passwords do not match': 'As novas senhas não conferem',
  'Password must be at least 8 characters long': 'A senha deve ter pelo menos 8 caracteres',
  'Password changed successfully': 'Senha alterada com sucesso',
  'Failed to change password': 'Falha ao alterar senha',
  'Remote action canceled by user.': 'Ação remota cancelada pelo usuário.',
  'Running remote action...': 'Executando ação remota...',
  'Remote action added to queue.': 'Ação remota adicionada à fila.',
};

const ptToEn: Record<string, string> = {
  'Painel': 'Dashboard',
  'Tarefas': 'Tasks',
  'Histórico WK': 'WK History',
  'Termos': 'Terms',
  'Usuários': 'Users',
  'Configurações de administrador': 'Admin Settings',
  'Configurações': 'Settings',
  'Central de comando': 'Command Center',
  'Logado como': 'Logged in as',
  'Sair': 'Logout',
  'Atualizar': 'Refresh',
  'Salvar': 'Save',
  'Salvando...': 'Saving...',
  'Configurações operacionais do WMT.': 'Operational settings for WMT.',
  'Idioma da interface': 'Interface language',
  'Escolha o idioma usado pelo WMT nesta workstation.': 'Choose the language used by WMT on this workstation.',
  'Idioma': 'Language',
  'Inglês': 'English',
  'Ingles': 'English',
  'Português': 'Portuguese',
  'Portugues': 'Portuguese',
  'Timeouts e polling': 'Timeouts and polling',
  'Scripts habilitados': 'Enabled scripts',
  'Caminho padrão de destino': 'Default destination path',
  'Aliases de ações remotas': 'Remote action aliases',
  'JSON simples. Ex.:': 'Simple JSON. Example:',
  'Configurações salvas': 'Settings saved',
  'Falha ao salvar configurações': 'Failed to save settings',
  'Verifique os campos informados.': 'Check the fields and try again.',
  'Log de diagnóstico': 'Diagnostic log',
  'Pacote visual de diagnóstico': 'Visual diagnostic package',
  'Inventário detalhado': 'Detailed inventory',
  'Limpeza': 'Cleanup',
  'Sistema': 'System',
  'Discos e BitLocker': 'Disks and BitLocker',
  'Softwares instalados': 'Installed software',
  'Ações remotas': 'Remote Actions',
  'Ações rápidas': 'Quick Actions',
  'Gerando diagnóstico visual...': 'Generating visual diagnostic...',
  'Consultando...': 'Consulting...',
  'Nenhum disco retornado.': 'No disk returned.',
  'Nenhum software instalado retornado.': 'No installed software returned.',
  'Senha atual': 'Current Password',
  'Nova senha': 'New Password',
  'Confirmar senha': 'Confirm Password',
  'Informe a senha atual': 'Enter current password',
  'Informe a nova senha': 'Enter new password',
  'Confirme a nova senha': 'Confirm new password',
  'Pesquisar usuários': 'Search Users',
  'Pesquisar por usuário ou email...': 'Search by username or email...',
  'Perfil': 'Role',
  'Senha': 'Password',
  'Informe o usuário': 'Enter username',
  'Informe o email': 'Enter email',
  'Informe a senha': 'Enter password',
  'Destino': 'Destination',
  'Histórico': 'History',
  'Início': 'Start',
  'Origem': 'Source',
  'Tarefas remotas': 'Remote Tasks',
  'Ativas': 'Active',
  'Concluídas': 'Completed',
  'Falhas': 'Failed',
  'Canceladas': 'Canceled',
  'Histórico da workstation': 'Workstation History',
  'Diagnósticos': 'Diagnostics',
  'Erros': 'Errors',
  'Usuário atual': 'Current user',
  'Endereço IP': 'IP Address',
  'Endereço MAC': 'MAC Address',
  'Último boot': 'Last Boot',
  'Fabricante': 'Manufacturer',
  'Modelo': 'Model',
  'Número de série': 'Serial Number',
  'Sistema operacional': 'Operating System',
  'Processador': 'Processor',
  'Atualizações': 'Updates',
  'Host selecionado:': 'Selected host:',
  'Informe uma workstation primeiro.': 'Enter a workstation first.',
  'DOCX gerado e pronto': 'DOCX generated and ready',
  'Nome completo do funcionário': 'Employee full name',
  'Nome': 'Name',
  'A prévia de impressão ainda não está pronta.': 'Print preview is not ready yet.',
};

function translateText(text: string, language: DisplayLanguage) {
  const trimmed = text.trim();
  if (!trimmed) return text;
  const translated = language === 'pt-BR' ? enToPt[trimmed] : ptToEn[trimmed];
  if (!translated) return text;
  return text.replace(trimmed, translated);
}

function translateDocument(language: DisplayLanguage) {
  const translateNode = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE && node.textContent) {
      const parent = node.parentElement;
      if (!parent || ['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE'].includes(parent.tagName)) return;
      node.textContent = translateText(node.textContent, language);
      return;
    }

    if (node instanceof HTMLElement) {
      if (node instanceof HTMLInputElement && node.placeholder) {
        node.placeholder = translateText(node.placeholder, language);
      }
      if (node.title) {
        node.title = translateText(node.title, language);
      }
      node.childNodes.forEach(translateNode);
    }
  };

  translateNode(document.body);
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<DisplayLanguage>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'pt-BR' || stored === 'en-US' ? stored : 'en-US';
  });

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'pt-BR' || stored === 'en-US') {
      return;
    }

    let cancelled = false;
    fetch(`${API_BASE_URL}/api/app-preferences`)
      .then((response) => response.ok ? response.json() : null)
      .then((payload: { display_language?: DisplayLanguage } | null) => {
        if (!cancelled && (payload?.display_language === 'pt-BR' || payload?.display_language === 'en-US')) {
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
    document.documentElement.lang = language === 'pt-BR' ? 'pt-BR' : 'en-US';
    const run = () => translateDocument(language);
    window.setTimeout(run, 0);
    const observer = new MutationObserver(run);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [language]);

  const value = useMemo<LanguageContextValue>(() => ({
    language,
    setLanguage: (next) => {
      setLanguageState(next);
      localStorage.setItem(STORAGE_KEY, next);
    },
    t: (text) => translateText(text, language),
  }), [language]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used inside LanguageProvider');
  }
  return context;
}
