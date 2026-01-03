# Jaiminho Notificações

Multi-tenant cloud notification system built on AWS Lambda, designed for WhatsApp message ingestion, intelligent urgency detection, and outbound notifications.

## System Architecture

### Key Components

- **WhatsApp Ingestion**: W-API integration with per-tenant instance management
- **Urgency Detection**: Deterministic rule engine (executed before any LLM usage)
- **Daily Digest**: Scheduled digest generation via EventBridge
- **Outbound Notifications**: SendPulse integration for official WhatsApp channel
- **Orchestration**: LangGraph-powered workflows for message processing

### Technical Stack

- **Runtime**: AWS Lambda (Python 3.11)
- **Storage**: DynamoDB (with strong tenant isolation by `user_id`)
- **IaC**: Terraform (all editable via GitHub Web)
- **Message Processing**: LangGraph
- **CI/CD**: GitHub Actions

## Project Structure

```
├── src/jaiminho_notificacoes/       # Main application code
│   ├── core/                        # Tenant isolation, config, logging
│   ├── ingestion/                   # WhatsApp message ingestion
│   ├── processing/                  # Urgency detection, digest, orchestration
│   ├── outbound/                    # SendPulse notifications
│   ├── persistence/                 # DynamoDB models and operations
│   └── lambda_handlers/             # AWS Lambda entry points
├── terraform/                        # Infrastructure as Code
│   ├── environments/                # dev, staging, prod configurations
│   └── *.tf                         # Terraform modules
├── tests/                           # Unit and integration tests
├── config/                          # Configuration files and schemas
├── docs/                            # Architecture and implementation guides
└── scripts/                         # Deployment and utility scripts
```

## Tenant Isolation Strategy

All data access is scoped to `user_id`:
- DynamoDB partition key: `user_id`
- Lambda context includes tenant information
- All API calls validate tenant context before data access
- See [docs/TENANT_ISOLATION.md](docs/TENANT_ISOLATION.md) for details

## Local Development

```bash
# Install development dependencies
pip install -r requirements/dev.txt

# Run tests
make test

# Start local environment
make local-run
```

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) for detailed setup.

## Deployment

Infrastructure is managed entirely via Terraform:

```bash
# Review changes
terraform plan -var-file="terraform/environments/prod.tfvars"

# Deploy
terraform apply -var-file="terraform/environments/prod.tfvars"
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full deployment guide.

## API Integration

- **W-API**: WhatsApp message ingestion webhooks
- **SendPulse**: Outbound notification delivery

See [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md) for integration details.

## Message Processing Workflow

LangGraph orchestrates the following pipeline:
1. Ingest WhatsApp message
2. Extract text and metadata
3. Apply deterministic urgency rules
4. (Optional) LLM analysis for non-urgent messages
5. Store in DynamoDB (tenant-scoped)
6. Queue for daily digest or immediate notification

See [docs/LANGGRAPH_WORKFLOWS.md](docs/LANGGRAPH_WORKFLOWS.md) for workflow details.

## Contributing

All files are editable via GitHub Web interface. Follow the existing structure and update relevant documentation when adding features.

## Version

Current version: `0.1.0` (see [version.txt](version.txt))