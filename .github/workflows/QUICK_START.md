# 🚀 Quick Start - Deploy Automático (Self-Hosted Runner)

Guia rápido para configurar deploy automático do PNCP Jobs no Hetzner.

## 📝 Setup em 5 Minutos

### 1️⃣ No Servidor Hetzner

```bash
# Conectar
ssh pncp@135.181.44.221

# Criar diretório e baixar runner
sudo mkdir -p /opt/actions-runner && sudo chown pncp:pncp /opt/actions-runner
cd /opt/actions-runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz && rm *.tar.gz

# Instalar rsync se necessário
sudo apt install -y rsync
```

### 2️⃣ No GitHub (Navegador)

1. Abra: `https://github.com/SEU_USUARIO/vercel_saas/settings/actions/runners/new`
2. Selecione: **Linux** → **x64**
3. Copie o comando `./config.sh --url ... --token ...`

### 3️⃣ De Volta ao Servidor

```bash
# Cole o comando copiado do GitHub (exemplo):
./config.sh --url https://github.com/USUARIO/vercel_saas --token ABC123TOKEN

# Quando perguntar, pressione Enter em tudo (aceitar padrões)

# Instalar como serviço
sudo ./svc.sh install pncp
sudo ./svc.sh start
sudo ./svc.sh status
```

### 4️⃣ No Seu PC (Local)

```bash
cd c:\projects\vercel_saas

# Commit e push
git add .github/workflows/
git commit -m "feat: Configure self-hosted runner for auto-deploy"
git push origin main
```

### 5️⃣ Verificar

- GitHub → **Actions** → Veja deploy rodando
- GitHub → **Settings** → **Actions** → **Runners** → Ver "pncp-hetzner" **Idle** (verde)

---

## ✅ Pronto!

Agora todo `git push origin main` vai fazer deploy automaticamente!

---

## 🔍 Comandos Úteis

```bash
# Ver status do runner
sudo systemctl status actions.runner.*.service

# Reiniciar runner
cd /opt/actions-runner && sudo ./svc.sh restart

# Ver logs do runner
sudo journalctl -u actions.runner.*.service -f

# Testar deploy manual no servidor
cd /opt/pncp-jobs
source venv/bin/activate
python scripts/run_pipeline.py
```

---

## 🆘 Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| Runner offline | `sudo systemctl restart actions.runner.*.service` |
| "No runner matching labels" | Verificar se runner está verde no GitHub |
| "rsync: command not found" | `sudo apt install -y rsync` |
| "Permission denied" | `sudo chown -R pncp:pncp /opt/pncp-jobs` |
| Deploy não executa | Verificar logs: `sudo journalctl -u actions.runner.*.service` |

---

## 📚 Documentação Completa

- **[RUNNER_SETUP.md](RUNNER_SETUP.md)** - Setup detalhado do runner
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Checklist completo
- **[SECRETS_SETUP.md](SECRETS_SETUP.md)** - Por que não precisa de secrets
- **[../deployment/HETZNER_SETUP.md](../deployment/HETZNER_SETUP.md)** - Setup completo do servidor

---

## 🎯 Arquitetura

```
GitHub Repository
    ↓ (push)
GitHub Actions detecta push
    ↓
Runner no Servidor Hetzner (/opt/actions-runner)
    ↓ (executa workflow)
Checkout código ($GITHUB_WORKSPACE)
    ↓ (rsync)
Atualiza /opt/pncp-jobs
    ↓
Atualiza dependências (pip install)
    ↓
Health check + Notificação
```

---

## ⚡ Por que Self-Hosted Runner?

- ✅ **Sem secrets SSH** - Mais seguro
- ✅ **Sem firewall issues** - Roda localmente
- ✅ **Mais rápido** - Sem latência de rede
- ✅ **Mais confiável** - Sem timeouts
- ✅ **Mais simples** - Setup único

---

**Setup completo em ~5 minutos!** 🚀
