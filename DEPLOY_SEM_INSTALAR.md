# 🚀 Deploy na AWS SEM Instalar Nada

**Método 100% na Nuvem** - Apenas GitHub, GitHub Actions e AWS Console

---

## ✅ PARTE 1: PREPARAÇÃO AWS (ÚNICA VEZ)

### Passo 1: Criar Conta AWS

1. Abra: https://aws.amazon.com
2. Clique em **"Criar uma Conta AWS"**
3. Preencha email, senha e dados da empresa
4. Confirme email e faça login

---

### Passo 2: Criar Usuário IAM para GitHub Actions

**Por que?** GitHub Actions vai fazer o deploy automaticamente. Precisa de uma conta segura.

1. Abra AWS Console: https://console.aws.amazon.com/
2. Digite **"IAM"** na barra de busca
3. Clique em **IAM** → **Usuários** (menu esquerdo)
4. Clique em **"Criar usuário"**

```
Nome: github-actions-deployer
☑ Fornecer acesso do console do gerenciamento AWS
Clique: Próximo
```

5. **Permissões:** Clique em **"Anexar políticas diretamente"**
   - Procure e marque: **AdministratorAccess**
   - Clique: **"Próximo"**

6. Clique: **"Criar usuário"**

7. **IMPORTANTE - Salvar Credenciais:**
   - Clique no usuário criado
   - Vá para **"Credenciais de segurança"**
   - Clique em **"Criar chave de acesso"**
   - Selecione: **Interface de Linha de Comando (CLI)**
   - Clique: **"Próximo"** → **"Criar chave de acesso"**
   - **COPIE E SALVE:**
     - Access Key ID
     - Secret Access Key

---

### Passo 3: Criar Bucket S3 para Terraform State

1. Abra AWS Console
2. Procure por **"S3"**
3. Clique em **"Criar bucket"**
4. Nome: `jaiminho-terraform-state-123456` (número único)
5. Deixe as outras opções padrão
6. Clique: **"Criar bucket"**

---

## 🔐 PARTE 2: CONFIGURAR GITHUB

### Passo 4: Adicionar Segredos no GitHub

1. Abra seu repositório no GitHub: https://github.com/lunathiago/jaiminho-notificacoes
2. Clique em **Settings** (⚙️ engrenagem)
3. No menu esquerdo, clique em **Secrets and variables** → **Actions**
4. Clique em **"New repository secret"**

Adicione **EXATAMENTE ESTES** segredos:

#### 4.1 - AWS_ACCESS_KEY_ID
- **Nome:** `AWS_ACCESS_KEY_ID`
- **Valor:** Cole a Access Key que você salvou
- Clique: **"Add secret"**

#### 4.2 - AWS_SECRET_ACCESS_KEY
- **Nome:** `AWS_SECRET_ACCESS_KEY`
- **Valor:** Cole a Secret Access Key
- Clique: **"Add secret"**

#### 4.3 - TERRAFORM_BACKEND_BUCKET
- **Nome:** `TERRAFORM_BACKEND_BUCKET`
- **Valor:** `jaiminho-terraform-state-123456` (nome do bucket S3)
- Clique: **"Add secret"**

#### 4.4 - DB_MASTER_PASSWORD
- **Nome:** `DB_MASTER_PASSWORD`
- **Valor:** Uma senha forte (ex: `SenhaForte123!@#`)
- Clique: **"Add secret"**

#### 4.5 - WAPI_API_KEY
- **Nome:** `WAPI_API_KEY`
- **Valor:** Sua chave da API W-API
- Clique: **"Add secret"**

#### 4.6 - SENDPULSE_API_KEY
- **Nome:** `SENDPULSE_API_KEY`
- **Valor:** Sua chave da API SendPulse
- Clique: **"Add secret"**

---

### Passo 5: Criar o Arquivo de Automação

1. No seu repositório GitHub, clique em **"Add file"** → **"Create new file"**
2. Nome do arquivo: `.github/workflows/deploy.yml`

3. Cole este conteúdo:

```yaml
name: Deploy para AWS

on:
  push:
    branches:
      - main
  workflow_dispatch:

env:
  AWS_REGION: us-east-1
  AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
  AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
  TF_VAR_environment: prod
  TF_VAR_aws_region: us-east-1
  TF_VAR_project_name: jaiminho-notificacoes
  TF_VAR_lambda_memory_size: 512
  TF_VAR_lambda_timeout: 60
  TF_VAR_db_instance_class: db.t4g.micro
  TF_VAR_db_allocated_storage: 20
  TF_VAR_db_max_allocated_storage: 100
  TF_VAR_db_master_username: admin
  TF_VAR_db_master_password: ${{ secrets.DB_MASTER_PASSWORD }}
  TF_VAR_wapi_api_key: ${{ secrets.WAPI_API_KEY }}
  TF_VAR_sendpulse_api_key: ${{ secrets.SENDPULSE_API_KEY }}

jobs:
  terraform:
    name: Terraform Plan & Apply
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout código
        uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.7.0

      - name: Terraform Init
        working-directory: ./terraform
        run: |
          terraform init \
            -backend-config="bucket=${{ secrets.TERRAFORM_BACKEND_BUCKET }}" \
            -backend-config="key=prod/terraform.tfstate" \
            -backend-config="region=us-east-1" \
            -backend-config="encrypt=true"

      - name: Terraform Plan
        working-directory: ./terraform
        run: terraform plan -out=tfplan

      - name: Terraform Apply
        working-directory: ./terraform
        if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'
        run: terraform apply -auto-approve tfplan

      - name: Export Outputs
        working-directory: ./terraform
        run: terraform output -json > terraform-outputs.json

      - name: Upload do Código para Lambda
        run: |
          # Instalar dependências
          pip install -q -r requirements/prod.txt
          
          # Empacotar código
          zip -r lambda_code.zip src/ config/ -q
          
          # Fazer upload
          for func in jaiminho-prod-message-orchestrator jaiminho-prod-daily-digest jaiminho-prod-feedback-handler; do
            aws lambda update-function-code \
              --function-name $func \
              --zip-file fileb://lambda_code.zip \
              --region us-east-1 || echo "Função $func não existe ainda (primeira execução)"
          done

      - name: Exibir URL da API
        run: |
          echo "✅ Deploy concluído!"
          echo ""
          echo "API Gateway URL:"
          terraform -chdir=./terraform output -raw api_gateway_url 2>/dev/null || echo "Em processamento..."
```

4. Na mensagem de commit, escreva: `Setup: Adicionar GitHub Actions para deploy automático`
5. Clique: **"Commit changes"**

---

## 🚀 PARTE 3: FAZER O PRIMEIRO DEPLOY

### Passo 6: Ativar o Deploy Automático

1. Abra seu repositório no GitHub
2. Clique na aba **"Actions"**
3. Na esquerda, clique em **"Deploy para AWS"**
4. Clique em **"Run workflow"**
5. Clique no botão verde **"Run workflow"**

Agora GitHub Actions vai:
- ⬇️ Baixar o código
- 🔧 Instalar ferramentas automaticamente
- 🌍 Criar infraestrutura na AWS
- 📤 Fazer upload do código
- ✅ Tudo em 10-20 minutos

---

### Passo 7: Acompanhar o Deploy

1. Clique na aba **"Actions"**
2. Clique no workflow que está rodando
3. Veja o progresso em tempo real

Se tudo der certo, você verá:
- ✅ Terraform Init
- ✅ Terraform Plan
- ✅ Terraform Apply
- ✅ Upload do Código para Lambda
- ✅ Exibir URL da API

---

## 📝 PARTE 4: FAZER ATUALIZAÇÕES FUTURAMENTE

### Atualizando o Código

**Tudo que você precisa fazer é:**

1. Editar um arquivo no GitHub (ou fazer push de uma branch)
2. Abrir um Pull Request
3. Fazer merge na branch `main`

Automaticamente, GitHub Actions vai:
- Fazer o deploy
- Atualizar a infraestrutura
- Enviar código novo

**Exemplo: Editar arquivo direto no GitHub**

1. No repositório, abra qualquer arquivo em `src/`
2. Clique no lápis (✏️ Edit)
3. Faça sua alteração
4. Clique em **"Commit changes"**
5. Clique em **"Commit directly to main"**
6. Clique em **"Commit changes"**

✅ GitHub Actions automaticamente vai fazer o novo deploy!

---

## 🧪 PARTE 5: CONFIGURAR WEBHOOKS

### Passo 8: Obter URL da API

Após o deploy terminar:

1. Abra AWS Console: https://console.aws.amazon.com/
2. Procure por **"API Gateway"**
3. Clique em **"jaiminho-prod-api"**
4. No menu esquerdo, clique em **"Fases"**
5. Clique em **"prod"** (ou "live")
6. Você verá a URL: `https://xxxxx.execute-api.us-east-1.amazonaws.com`

**Salve essa URL!**

---

### Passo 9: Configurar W-API

1. Acesse seu painel W-API
2. Vá para **Webhooks** ou **Integrações**
3. Configure a URL: 
   ```
   https://xxxxx.execute-api.us-east-1.amazonaws.com/webhook
   ```
4. Clique em **Salvar**

---

### Passo 10: Configurar SendPulse

1. Acesse seu painel SendPulse
2. Vá para **Integrações** ou **Webhooks**
3. Configure a URL:
   ```
   https://xxxxx.execute-api.us-east-1.amazonaws.com/feedback
   ```
4. Clique em **Salvar**

---

## 📊 PARTE 6: MONITORAMENTO

### Passo 11: Ver Logs da Aplicação

1. Abra AWS Console
2. Procure por **"CloudWatch"**
3. Clique em **"Logs"** → **"Grupos de logs"**
4. Procure por:
   - `/aws/lambda/jaiminho-prod-message-orchestrator`
   - `/aws/lambda/jaiminho-prod-daily-digest`
   - `/aws/lambda/jaiminho-prod-feedback-handler`

5. Clique em um e veja os logs

---

### Passo 12: Receber Notificações de Erro

1. Abra AWS Console
2. Procure por **"SNS"** (Simple Notification Service)
3. Clique em **"Tópicos"**
4. Procure por `jaiminho-prod-alarms`
5. Clique em **"Criar Assinatura"**
6. Protocolo: **Email**
7. Ponto de extremidade: **seu@email.com**
8. Clique em **"Criar assinatura"**
9. **Confirme no seu email**

Agora você recebe notificações de erros automaticamente!

---

## 📱 PARTE 7: FAZER NOVAS ALTERAÇÕES

### Cenário: Você quer mudar o tamanho do Lambda

1. Abra seu repositório GitHub
2. Vá para `terraform/environments/prod.tfvars`
3. Clique no lápis (✏️ Edit)
4. Encontre a linha:
   ```
   lambda_memory_size = 512
   ```
5. Mude para:
   ```
   lambda_memory_size = 1024
   ```
6. Clique em **"Commit changes"** → **"Commit directly to main"**

GitHub Actions automaticamente vai:
- Atualizar a infraestrutura
- Aumentar a memória do Lambda

✅ Tudo sem instalar nada localmente!

---

## 🎯 CHECKLIST FINAL

- ✅ Conta AWS criada
- ✅ Usuário IAM com credenciais salvas
- ✅ Bucket S3 criado para Terraform state
- ✅ Segredos adicionados ao GitHub
- ✅ Arquivo `.github/workflows/deploy.yml` criado
- ✅ Primeiro deploy executado com sucesso
- ✅ Webhooks configurados (W-API e SendPulse)
- ✅ Logs visíveis no CloudWatch
- ✅ Alarmes configurados

---

## 🆘 TROUBLESHOOTING

### Problema: "Deploy falhou com erro 'Access Denied'"
**Solução:** Verifique se as credenciais AWS estão corretas no GitHub Secrets

```
Settings → Secrets and variables → Actions
Verifique: AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY
```

### Problema: "Terraform state bucket não encontrado"
**Solução:** Confira se o nome do bucket está correto:
- GitHub → Settings → Secrets
- Procure: `TERRAFORM_BACKEND_BUCKET`
- Verifique se é igual ao bucket criado no AWS S3

### Problema: "Lambda functions não foram atualizadas"
**Solução:** É normal na primeira execução. Na segunda vez funcionará.

Execute manualmente:
1. GitHub → Actions
2. Clique em "Deploy para AWS"
3. Clique em "Run workflow"

### Problema: "Webhooks retornam 403 ou 404"
**Solução:** 
1. Aguarde 2 minutos após o deploy
2. Verifique a URL da API no CloudWatch
3. Confirme que W-API e SendPulse estão com a URL correta

---

## 📚 O QUE VOCÊ PODE FAZER VIA GITHUB

✅ Editar código  
✅ Alterar configurações  
✅ Adicionar novas features  
✅ Ver histórico de deploys  
✅ Reverter alterações  

Tudo sem instalar uma única ferramenta!

---

## 🔄 WORKFLOW TÍPICO

1. **Segunda-feira:** Você edita um arquivo no GitHub
2. **Automaticamente:** GitHub Actions faz deploy
3. **Terça-feira:** Você quer reverter
   - Git → Revert commit
   - Novo deploy automático
4. **Quarta-feira:** Quer aumentar memória Lambda
   - Edita `prod.tfvars`
   - Commit
   - GitHub Actions atualiza

**Tudo na web, sem terminal, sem instalações!** 🎉

---

## 💡 PRO TIPS

### Dica 1: Usar Branch para Testes
```
1. Crie nova branch: "testing"
2. Faça alterações
3. Veja o diff antes de fazer merge
4. Se aprovado, faça merge para main
5. Deploy automático acontece
```

### Dica 2: Monitorar Logs em Tempo Real
```
AWS Console → CloudWatch → Logs
Clique em "tail" para ver logs ao vivo
```

### Dica 3: Economizar Custos
Se não usar por um tempo, pode pausar:
```
AWS Console → Lambda
Clique em cada função
Agende para ser desligada
```

---

**Versão:** 1.0.0  
**Última Atualização:** Janeiro 2026  
**Método:** 100% GitHub Actions + AWS
