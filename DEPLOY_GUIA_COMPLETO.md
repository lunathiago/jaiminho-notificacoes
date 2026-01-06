# 🚀 Guia Completo de Deploy - Jaiminho Notificações

## Para Usuários Não-Técnicos

**O que é este guia?**
Um passo a passo simples para colocar a aplicação no ar na AWS (computação em nuvem). Você não precisa ser um especialista em tecnologia.

---

## ✅ PARTE 1: PREPARAÇÃO INICIAL

### Passo 1: Criar uma Conta AWS (se não tiver)

1. Abra: https://aws.amazon.com
2. Clique em **"Criar uma Conta AWS"** (canto superior direito)
3. Preencha:
   - Email corporativo
   - Senha forte (misture letras, números, símbolos)
   - Nome da empresa
   - Endereço

4. AWS pedirá seu cartão de crédito
   - Você vai usar a **camada gratuita** inicialmente
   - Faremos o deploy de forma otimizada

5. Confirme o email da AWS
6. Faça login com suas credenciais

---

### Passo 2: Criar um Usuário IAM (Segurança)

**O que é?** Um usuário seguro com permissões limitadas (melhor do que usar a conta principal)

1. Abra o AWS Console: https://console.aws.amazon.com/
2. No topo direito, digite **"IAM"** na barra de busca
3. Clique em **IAM** → **Usuários** (menu esquerdo)
4. Clique em **"Criar usuário"**

```
Nome do usuário: jaiminho-deploy
☑ Fornecer acesso do console do gerenciamento AWS
☑ Quero criar um usuário do IAM
Clique em: Próximo
```

5. Na tela de permissões:
   - Clique em **"Anexar políticas diretamente"**
   - Procure por: **AdministratorAccess**
   - ☑ Selecione **AdministratorAccess**
   - Clique em **"Próximo"**

6. Clique em **"Criar usuário"**

7. **Importante:** Clique no usuário criado
   - Vá para **"Credenciais de segurança"**
   - Clique em **"Criar chave de acesso"**
   - Selecione: **Interface de Linha de Comando (CLI)**
   - Clique em **"Próximo"**
   - Clique em **"Criar chave de acesso"**
   - **SALVE ESTE ARQUIVO** em lugar seguro

---

### Passo 3: Preparar o Computador Local

Você precisa de 3 ferramentas instaladas:

#### 3.1 - Instalar AWS CLI

**Windows:**
1. Baixe: https://awscli.amazonaws.com/AWSCLIV2.msi
2. Execute o instalador
3. Clique "Next" até terminar

**macOS:**
```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.zip" -o "AWSCLIV2.zip"
unzip AWSCLIV2.zip
sudo ./aws/install
```

**Linux:**
```bash
sudo apt update
sudo apt install awscli
```

Verifique se funcionou:
```bash
aws --version
```

---

#### 3.2 - Configurar AWS CLI com suas Credenciais

Abra o terminal/prompt de comando e execute:

```bash
aws configure
```

Responda:

```
AWS Access Key ID: [Cole a Access Key que você salvou]
AWS Secret Access Key: [Cole a Secret Access Key]
Default region name: us-east-1
Default output format: json
```

---

#### 3.3 - Instalar Terraform

**Windows:**
1. Baixe: https://www.terraform.io/downloads
2. Escolha Windows → download o arquivo ZIP
3. Descompacte para: `C:\terraform`
4. Adicione ao PATH do Windows (veja tutorial online)

**macOS:**
```bash
brew install terraform
```

**Linux:**
```bash
wget https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip
unzip terraform_1.7.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/
```

Verifique se funcionou:
```bash
terraform --version
```

---

#### 3.4 - Instalar Git

**Windows:**
1. Baixe: https://git-scm.com/download/win
2. Execute o instalador

**macOS:**
```bash
brew install git
```

**Linux:**
```bash
sudo apt install git
```

---

### Passo 4: Clonar o Projeto

No terminal/prompt, execute:

```bash
git clone https://github.com/lunathiago/jaiminho-notificacoes.git
cd jaiminho-notificacoes
```

---

## 📦 PARTE 2: PREPARAR A INFRAESTRUTURA AWS

### Passo 5: Criar Bucket S3 para Terraform State

O Terraform precisa armazenar o "estado" da infraestrutura. Faremos no AWS S3 (storage em nuvem).

No terminal, execute:

```bash
aws s3 mb s3://jaiminho-terraform-state-$(date +%s) --region us-east-1
```

**Copie o nome do bucket criado.** Você vai usar no próximo passo.

---

### Passo 6: Criar Arquivo de Configuração

No seu editor de texto (VS Code, Sublime, Notepad++), crie um arquivo chamado:

`backend-config.txt`

Com o seguinte conteúdo:

```
bucket         = "jaiminho-terraform-state-AQUI_COLE_O_NUMERO"
key            = "prod/terraform.tfstate"
region         = "us-east-1"
encrypt        = true
dynamodb_table = "terraform-locks"
```

Salve o arquivo na pasta `terraform/` do projeto.

---

### Passo 7: Configurar Variáveis de Produção

Abra o arquivo: `terraform/environments/prod.tfvars`

Edite conforme sua configuração:

```hcl
project_name            = "jaiminho-notificacoes"
environment             = "prod"
aws_region              = "us-east-1"

# Lambda
lambda_memory_size      = 512        # RAM em MB
lambda_timeout          = 60         # Tempo máximo em segundos

# Banco de dados
db_instance_class       = "db.t4g.micro"      # Tipo mais barato
db_allocated_storage    = 20                  # 20 GB inicialmente
db_max_allocated_storage = 100                # Pode crescer até 100 GB

# Rede
vpc_cidr                = "10.0.0.0/16"

# SQS
sqs_message_retention_seconds = 86400         # 1 dia
```

---

### Passo 8: Inicializar Terraform

No terminal, dentro da pasta `terraform/`, execute:

```bash
cd terraform

terraform init -backend-config=backend-config.txt
```

Você verá mensagens assim:

```
Initializing the backend...
...
Successfully configured the backend "s3"!
Initializing provider plugins...
...
Terraform has been successfully initialized!
```

✅ Se vir **"Successfully initialized"**, está tudo ok!

---

## 🔐 PARTE 3: CONFIGURAR SEGREDOS (Credenciais)

### Passo 9: Preparar Arquivo com Credenciais Secretas

Você precisa ter as credenciais das integrações. Crie um arquivo: `terraform/secrets.tfvars`

```hcl
# W-API (WhatsApp)
wapi_api_key        = "sua_api_key_wapi"
wapi_base_url       = "https://api.wapi.ai"

# SendPulse (Notificações)
sendpulse_api_key   = "sua_api_key_sendpulse"
sendpulse_list_id   = "seu_list_id"

# Banco de dados - CRIE UMA SENHA FORTE
db_master_username  = "admin"
db_master_password  = "SenhaForte123!@#"

# App Config
app_environment     = "production"
```

**⚠️ IMPORTANTE:** 
- Substitua pelos valores reais
- **Nunca** compartilhe este arquivo
- Adicione ao `.gitignore`

---

## 📊 PARTE 4: REVISAR E FAZER O DEPLOY

### Passo 10: Visualizar o Que Será Criado

No terminal (dentro de `terraform/`), execute:

```bash
terraform plan -var-file="environments/prod.tfvars" -var-file="secrets.tfvars"
```

Terraform vai mostrar:
- ✅ Recursos que serão **criados**
- 📝 Recursos que serão **modificados**
- ❌ Recursos que serão **deletados**

**Leia com atenção!** Se algo parecer errado, cancele (Ctrl+C).

---

### Passo 11: Executar o Deploy

Quando tudo estiver correto, execute:

```bash
terraform apply -var-file="environments/prod.tfvars" -var-file="secrets.tfvars"
```

Terraform vai pedir confirmação:

```
Do you want to perform these actions?
  Terraform will perform the actions described above.
  Only 'yes' will be accepted to approve.

  Enter a value:
```

**Digite: `yes`**

⏳ Aguarde 10-20 minutos. Terraform está criando:
- Banco de dados RDS
- Funções Lambda
- Filas SQS
- API Gateway
- Segurança e permissões

---

### Passo 12: Verificar o Deploy

Quando terminar, você verá:

```
Apply complete! Resources: X added, 0 changed, 0 destroyed.

Outputs:
api_gateway_url = "https://xxxxx.execute-api.us-east-1.amazonaws.com"
```

**Salve a URL da API!** Você vai precisar dela.

---

## 📤 PARTE 5: FAZER UPLOAD DO CÓDIGO

### Passo 13: Preparar o Código

Na raiz do projeto, execute:

```bash
# Instalar dependências
pip install -r requirements/prod.txt

# Empacotar o código
zip -r lambda_code.zip src/ config/ -x "*.pyc"
```

---

### Passo 14: Fazer Upload do Código para Lambda

```bash
aws lambda update-function-code \
  --function-name jaiminho-prod-message-orchestrator \
  --zip-file fileb://lambda_code.zip \
  --region us-east-1
```

Repita para as outras funções:

```bash
aws lambda update-function-code \
  --function-name jaiminho-prod-daily-digest \
  --zip-file fileb://lambda_code.zip \
  --region us-east-1

aws lambda update-function-code \
  --function-name jaiminho-prod-feedback-handler \
  --zip-file fileb://lambda_code.zip \
  --region us-east-1
```

✅ Quando terminar, o código está no ar!

---

## 🧪 PARTE 6: TESTAR E VALIDAR

### Passo 15: Testar a API

Abra o terminal e execute:

```bash
curl -X GET "https://xxxxx.execute-api.us-east-1.amazonaws.com/health"
```

Se funcionar, você verá:

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

### Passo 16: Configurar Webhooks (W-API e SendPulse)

1. **W-API:**
   - Acesse painel W-API
   - Vá para **Webhooks**
   - Configure URL: `https://xxxxx.execute-api.us-east-1.amazonaws.com/webhook`
   - Salve

2. **SendPulse:**
   - Acesse painel SendPulse
   - Vá para **Integrações**
   - Configure URL: `https://xxxxx.execute-api.us-east-1.amazonaws.com/feedback`
   - Salve

---

## 📊 PARTE 7: MONITORAMENTO

### Passo 17: Acessar os Logs

Abra: https://console.aws.amazon.com/cloudwatch

1. No menu esquerdo: **Logs** → **Grupos de Logs**
2. Procure por:
   - `/aws/lambda/jaiminho-prod-message-orchestrator`
   - `/aws/lambda/jaiminho-prod-daily-digest`
   - `/aws/lambda/jaiminho-prod-feedback-handler`

3. Clique em um e veja os logs da aplicação

---

### Passo 18: Criar Alarmes

No CloudWatch:

1. **Alarmes** → **Criar alarme**
2. Selecione **Métrica**
3. Procure pela função Lambda
4. Selecione: **Erros**
5. Configure:
   - **Limite:** 10 erros em 5 minutos
   - **Email:** seu@email.com
   - Clique em **Criar alarme**

---

## 🎯 CHECKLIST FINAL

Antes de considerar o deploy completo, verifique:

- ✅ AWS CLI instalado e configurado
- ✅ Terraform instalado
- ✅ Bucket S3 criado para state
- ✅ Arquivo `secrets.tfvars` com credenciais
- ✅ `terraform plan` sem erros
- ✅ `terraform apply` concluído com sucesso
- ✅ Código enviado para Lambda
- ✅ Webhooks configurados
- ✅ Testes básicos funcionando
- ✅ Alarmes configurados

---

## 🆘 TROUBLESHOOTING

### Problema: "Access Denied"
**Solução:** Verifique se suas credenciais AWS estão corretas:
```bash
aws sts get-caller-identity
```

### Problema: Terraform "Resource already exists"
**Solução:** O recurso já foi criado antes. Execute:
```bash
terraform import [resource-type].[resource-name] [aws-resource-id]
```

### Problema: Lambda "Permission denied to write logs"
**Solução:** Verifique as permissões IAM. Re-execute:
```bash
terraform apply -var-file="environments/prod.tfvars" -var-file="secrets.tfvars"
```

### Problema: API retorna 500 error
**Solução:** Verifique os logs no CloudWatch:
```bash
aws logs tail /aws/lambda/jaiminho-prod-message-orchestrator --follow
```

---

## 📞 PRÓXIMOS PASSOS

1. **Monitorar** os logs e alarmes regularmente
2. **Escalar** os recursos conforme o volume cresce
3. **Fazer backup** do banco de dados
4. **Configurar** CI/CD para atualizações automáticas
5. **Documentar** qualquer customização realizada

---

## 📚 RECURSOS ADICIONAIS

- [Documentação AWS Lambda](https://docs.aws.amazon.com/lambda/)
- [Documentação Terraform AWS](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Suporte AWS](https://console.aws.amazon.com/support/)
- [Documentação do Projeto](./docs/)

---

**Versão:** 1.0.0  
**Última Atualização:** Janeiro 2026  
**Criado para:** Jaiminho Notificações
