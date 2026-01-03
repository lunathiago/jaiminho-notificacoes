# Terraform Infrastructure - Jaiminho Notificações

Infraestrutura como código (IaC) para o projeto **jaiminho-notificacoes** usando Terraform.

## 📋 Visão Geral

Esta configuração Terraform provisiona toda a infraestrutura AWS necessária para executar o sistema de notificações Jaiminho:

### Recursos Provisionados

- **🌐 API Gateway HTTP API**: Endpoints para webhooks da W-API e feedback
- **⚡ AWS Lambda (Python 3.11)**:
  - `jaiminho_message_orchestrator`: Processa mensagens e roteia baseado em urgência
  - `jaiminho_daily_digest`: Gera e envia resumos diários
  - `jaiminho_feedback_handler`: Processa feedback de usuários
- **🗄️ RDS PostgreSQL 15**: Multi-tenant com isolamento por user_id
- **📬 SQS**: Fila de mensagens com DLQ para buffering e resiliência
- **⏰ EventBridge**: Agendamento para digest diário
- **🔐 Secrets Manager**: Gerenciamento seguro de credenciais
- **🔑 IAM Roles**: Políticas com least privilege
- **🌍 VPC**: Rede isolada com subnets públicas e privadas
- **📊 CloudWatch**: Logging e alarmes

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Gateway                              │
│                  /webhook  |  /feedback  |  /health             │
└────────────────┬─────────────────────┬──────────────────────────┘
                 │                     │
                 ▼                     ▼
        ┌────────────────┐    ┌────────────────┐
        │    Lambda      │    │    Lambda      │
        │  Orchestrator  │    │    Feedback    │
        └────────┬───────┘    └────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │   SQS Queue    │◄────── EventBridge (cron)
        └────────┬───────┘                │
                 │                        ▼
                 │               ┌────────────────┐
                 │               │    Lambda      │
                 │               │  Daily Digest  │
                 │               └────────┬───────┘
                 │                        │
                 ▼                        ▼
        ┌────────────────────────────────────┐
        │         RDS PostgreSQL              │
        │      (Multi-tenant + Isolation)     │
        └────────────────────────────────────┘
                          │
                          ▼
                 ┌────────────────┐
                 │   DynamoDB     │
                 │  (Messages,    │
                 │   Digests,     │
                 │   Tenants)     │
                 └────────────────┘
```

## 📦 Pré-requisitos

1. **Terraform** >= 1.5.0
2. **AWS CLI** configurado com credenciais válidas
3. **Permissões IAM** necessárias para criar recursos
4. **S3 Bucket** para backend do Terraform (state remoto)

### Instalação do Terraform

```bash
# macOS
brew install terraform

# Linux (Ubuntu/Debian)
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
```

## 🚀 Deployment

### 1. Configurar Backend (State Remoto)

Crie um bucket S3 para armazenar o state do Terraform:

```bash
aws s3 mb s3://jaiminho-terraform-state --region us-east-1
aws s3api put-bucket-versioning \
  --bucket jaiminho-terraform-state \
  --versioning-configuration Status=Enabled
```

### 2. Configurar Variáveis

Escolha o ambiente e copie o arquivo de variáveis correspondente:

```bash
# Para desenvolvimento
cp environments/dev.tfvars terraform.tfvars

# Para staging
cp environments/staging.tfvars terraform.tfvars

# Para produção
cp environments/prod.tfvars terraform.tfvars
```

Edite `terraform.tfvars` conforme necessário.

### 3. Inicializar Terraform

```bash
terraform init \
  -backend-config="bucket=jaiminho-terraform-state" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=us-east-1"
```

### 4. Validar Configuração

```bash
terraform validate
terraform fmt
```

### 5. Planejar Deploy

```bash
# Preview das mudanças
terraform plan -out=tfplan

# Com arquivo de variáveis específico
terraform plan -var-file="environments/dev.tfvars" -out=tfplan
```

### 6. Aplicar Mudanças

```bash
terraform apply tfplan
```

### 7. Ver Outputs

```bash
terraform output
terraform output -json > outputs.json
```

## 🔧 Pós-Deployment

Após o deploy bem-sucedido, execute as seguintes etapas:

### 1. Atualizar Secrets Manager

```bash
# W-API
aws secretsmanager put-secret-value \
  --secret-id $(terraform output -raw secret_wapi_arn) \
  --secret-string '{"api_key":"YOUR_KEY","api_url":"https://api.wapi.example.com","instance_id":"YOUR_INSTANCE"}'

# SendPulse
aws secretsmanager put-secret-value \
  --secret-id $(terraform output -raw secret_sendpulse_arn) \
  --secret-string '{"client_id":"YOUR_ID","client_secret":"YOUR_SECRET"}'
```

### 2. Deploy do Código Lambda

```bash
# Criar pacote de deployment
cd ../src
zip -r lambda_package.zip jaiminho_notificacoes/

# Upload para as Lambdas
aws lambda update-function-code \
  --function-name $(terraform output -raw lambda_orchestrator_name) \
  --zip-file fileb://lambda_package.zip

aws lambda update-function-code \
  --function-name $(terraform output -raw lambda_digest_name) \
  --zip-file fileb://lambda_package.zip

aws lambda update-function-code \
  --function-name $(terraform output -raw lambda_feedback_name) \
  --zip-file fileb://lambda_package.zip
```

### 3. Inicializar Banco de Dados

```bash
# Conectar ao RDS via bastion ou Lambda
# Execute scripts de inicialização do schema multi-tenant
python ../scripts/migrate_data.py
```

### 4. Configurar Webhook na W-API

Use o endpoint do webhook retornado por `terraform output webhook_endpoint`:

```bash
terraform output webhook_endpoint
# Output: https://xxxxx.execute-api.us-east-1.amazonaws.com/webhook
```

### 5. Testar Endpoints

```bash
# Health check
curl $(terraform output -raw api_gateway_url)/health

# Webhook (exemplo)
curl -X POST $(terraform output -raw webhook_endpoint) \
  -H "Content-Type: application/json" \
  -d '{"test":"data"}'
```

## 📊 Recursos por Ambiente

| Recurso | Dev | Staging | Prod |
|---------|-----|---------|------|
| RDS Instance | t4g.micro | t4g.small | t4g.medium |
| Lambda Memory | 256 MB | 512 MB | 1024 MB |
| Availability Zones | 1 | 2 | 3 |
| RDS Multi-AZ | ❌ | ❌ | ✅ |
| Backup Retention | 3 dias | 7 dias | 30 dias |

## 🔒 Segurança

### Tenant Isolation

- **RDS**: Dados isolados por `user_id` com Row-Level Security (RLS)
- **DynamoDB**: Partition key inclui `tenant_id`
- **IAM Policies**: Conditional access baseado em tenant tags

### Encryption

- ✅ RDS: Storage encryption at rest
- ✅ SQS: SSE-SQS encryption
- ✅ DynamoDB: Server-side encryption
- ✅ Secrets Manager: KMS encryption
- ✅ Lambda: Environment variables encryption

### Network Security

- ✅ VPC isolada com subnets privadas
- ✅ Security groups com regras restritas
- ✅ RDS não acessível publicamente
- ✅ NAT Gateway para acesso externo das Lambdas
- ✅ VPC Endpoints para reduzir custos e aumentar segurança

## 📈 Monitoramento

### CloudWatch Alarms

Alarmes configurados para:
- API Gateway 4xx/5xx errors
- Lambda errors e duration
- RDS CPU, storage, connections
- DynamoDB throttling
- SQS DLQ messages
- EventBridge failed invocations

### Logs

- API Gateway: `/aws/apigateway/jaiminho-notificacoes-{env}`
- Lambda: `/aws/lambda/jaiminho-notificacoes-{env}-{function}`
- RDS: CloudWatch Logs export ativado

## 💰 Estimativa de Custos

### Desenvolvimento (~$30-50/mês)
- RDS t4g.micro: ~$15
- Lambda (baixo uso): ~$5
- DynamoDB on-demand: ~$5
- NAT Gateway: ~$10
- Outros: ~$5-15

### Produção (~$200-400/mês)
- RDS t4g.medium Multi-AZ: ~$100
- Lambda (uso médio): ~$50
- DynamoDB on-demand: ~$30
- NAT Gateway (3 AZs): ~$100
- Outros: ~$20-120

## 🧹 Cleanup

Para destruir todos os recursos:

```bash
# ATENÇÃO: Isso vai deletar TODOS os recursos!
terraform destroy -var-file="environments/dev.tfvars"
```

Para ambientes de produção, certifique-se de:
1. Fazer backup do RDS
2. Exportar dados do DynamoDB
3. Revisar recursos com `deletion_protection`

## 📚 Estrutura de Arquivos

```
terraform/
├── main.tf              # Provider e configuração principal
├── variables.tf         # Definição de variáveis
├── outputs.tf           # Outputs do Terraform
├── vpc.tf              # VPC, subnets, security groups
├── rds.tf              # RDS PostgreSQL
├── lambda.tf           # Lambda functions
├── api_gateway.tf      # API Gateway HTTP API
├── eventbridge.tf      # EventBridge rules e targets
├── sqs.tf              # SQS queues e DLQ
├── dynamodb.tf         # DynamoDB tables
├── iam.tf              # IAM roles e policies
├── secrets.tf          # Secrets Manager
├── terraform.tfvars.example  # Exemplo de variáveis
└── environments/
    ├── dev.tfvars      # Variáveis de desenvolvimento
    ├── staging.tfvars  # Variáveis de staging
    └── prod.tfvars     # Variáveis de produção
```

## 🤝 Contribuindo

1. Sempre use `terraform fmt` antes de commit
2. Execute `terraform validate` para validar
3. Teste em ambiente de dev primeiro
4. Documente mudanças significativas

## 📝 Notas Importantes

- ⚠️ Secrets Manager tem valores placeholder - atualize após deploy
- ⚠️ Lambda deployment usa placeholder ZIP - faça upload do código real
- ⚠️ Ambientes de prod têm `deletion_protection` ativado
- ⚠️ Configure SNS topics para alarmes em produção
- ⚠️ Backend S3 requer bucket criado previamente

## 📞 Suporte

Para problemas ou dúvidas:
1. Verifique logs do CloudWatch
2. Revise outputs do Terraform
3. Consulte documentação AWS
4. Abra issue no repositório

---

**Versão**: 1.0.0  
**Terraform**: >= 1.5.0  
**AWS Provider**: ~> 5.0
