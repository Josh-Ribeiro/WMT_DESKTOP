# Runtime do backend

O WMT possui dois modos explícitos de execução.

## Central

É o padrão dos builds corporativos:

```powershell
.\scripts\build-and-release.ps1 `
  -BackendMode central `
  -BackendUrl https://wmt.example.com
```

O React usa o backend HTTPS configurado e o Tauri não inicia nenhum processo
Python local. O login Windows automático continua usando a identificação da
estação via conexão direta e WMI/CIM.

## Sidecar

Usado em uma edição local ou de diagnóstico:

```powershell
.\scripts\build-and-release.ps1 `
  -BackendMode sidecar `
  -Channel debug `
  -UpdateEndpoint https://wmt.example.com/api/updates/latest-debug.json
```

O build:

1. instala as dependências de `backend/requirements-build.txt`;
2. gera `wmt-backend.exe` com PyInstaller;
3. inclui o executável no MSI pelo `externalBin` do Tauri;
4. fixa a API local em `http://127.0.0.1:8000`.

O sidecar não depende de Python instalado na estação. Seu SQLite fica no
diretório de dados da aplicação, e os arquivos `backend.log` e
`backend-error.log` ficam no diretório de logs da aplicação.

O Tauri só encerra o processo que ele próprio iniciou. Se a porta 8000 estiver
ocupada, o processo encontrado precisa responder a `/health/live` com:

```json
{
  "status": "ok",
  "service": "wmt-backend",
  "api_version": 1
}
```

Um serviço diferente ou uma API incompatível não é reutilizado nem encerrado.

## Health checks

- `/health/live`: confirma processo, identidade e versão do contrato.
- `/health/ready`: também confirma que o repositório SQLite pode ser aberto.
- `/health`: alias compatível para clientes antigos, agora com identidade.

O frontend consulta `/health/ready` antes de restaurar a sessão ou iniciar o
login automático. Falhas e incompatibilidades são mostradas ao usuário com uma
opção de nova tentativa.

## Classificação de impressoras

O intervalo IPv4 `10.131.200.1` até `10.131.200.255` é reservado para
impressoras. Toda consulta nesse intervalo retorna `device_type: "printer"`,
inclusive quando o equipamento está offline ou quando o SNMP não responde.

Essa regra impede que o backend tente tratar esses endereços como estações WMI.
Fora do intervalo, a detecção continua usando nome do host, portas de impressão
e identificação via SNMP.
