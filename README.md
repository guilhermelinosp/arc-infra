# arc-infra

Infraestrutura do Actions Runner Controller (ARC) no cluster Talos.

## Estrutura

```
arc-infra/
├── runner-controller/           # Webhook controller (cria runners automaticamente)
│   ├── Dockerfile               # Imagem ghcr.io/guilhermelinosp/runner-controller
│   └── controller.py            # ~80 linhas, zero dependências
├── arc-helm/
│   └── values.yaml              # Helm values para instalar ARC
├── runner-templates/
│   └── runnerdeployment.yaml    # Template RunnerDeployment + HRA
└── k8s-manifests.yaml           # Deployment, Service, HTTPRoute, RBAC
```

## Como replicar

### 1. GitHub App

Criar App em: https://github.com/settings/apps/new

- Name: `arc-talos-cluster`
- Permissions: Administration (R&W), Actions (R&W), Metadata (R)
- Subscribe to events: Repository
- Instalar em: All repositories

### 2. Instalar ARC

```bash
helm repo add actions-runner-controller https://actions-runner-controller.github.io/actions-runner-controller
helm install arc actions-runner-controller/actions-runner-controller \
  -n arc-actions \
  --set authSecret.create=false \
  --set githubAppId=SEU_APP_ID \
  --set githubAppInstallationId=SEU_INSTALLATION_ID \
  --set githubAppPrivateKeySecretName=controller-manager
```

### 3. Deploy runner-controller

```bash
kubectl apply -n arc-actions -f k8s-manifests.yaml
```

### 4. Buildear imagem custom do runner (opcional)

```bash
docker build -t ghcr.io/SEU_USUARIO/arc-runner:latest .
docker push ghcr.io/SEU_USUARIO/arc-runner:latest
```

### 5. Criar RunnerDeployment pra um repo

```bash
kubectl apply -f runner-templates/runnerdeployment.yaml
```

## Webhook

O controller expõe `POST /` para receber webhooks do GitHub.
Configure no GitHub App: Payload URL = `https://webhook.seudominio.com`
# Test flow
# Trigger re-check
# Trigger
# Feature test
# Feat test 2
