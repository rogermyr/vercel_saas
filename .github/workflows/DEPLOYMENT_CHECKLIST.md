# Checklist de Deploy Automático - GitHub Actions → Hetzner

Use este checklist para configurar o deploy automático do PNCP Jobs.

## 📋 Checklist de Configuração

### 1. ✅ Arquivos Criados (Já Concluído)
- [x] `.github/workflows/deploy.yml` - workflow de deploy com self-hosted runner
- [x] `.github/workflows/RUNNER_SETUP.md` - guia de instalação do runner
- [x] `.github/workflows/DEPLOYMENT_CHECKLIST.md` - checklist completo
- [x] `deployment/verify_git_setup.sh` - script de verificação

### 2. 🔧 Configuração no Servidor Hetzner

#### 2.1. Instalar GitHub Self-Hosted Runner

**IMPORTANTE:** Agora usamos self-hosted runner ao invés de SSH. Isso elimina problemas de firewall.

```bash
# 1. Conecte-se ao servidor
ssh pncp@135.181.44.221

# 2. Crie diretório para o runner
sudo mkdir -p /opt/actions-runner
sudo chown pncp:pncp /opt/actions-runner
cd /opt/actions-runner

# 3. Baixe o GitHub Actions Runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
rm actions-runner-linux-x64-2.311.0.tar.gz
```

#### 2.2. Obter Token do GitHub (no navegador)

1. Abra: `https://github.com/SEU_USUARIO/vercel_saas/settings/actions/runners/new`
2. Selecione: **Linux** → **x64**
3. Copie o comando `./config.sh --url...` com o token

#### 2.3. Configurar Runner (no servidor)

```bash
# Cole o comando copiado acima (com o token)
./config.sh --url https://github.com/USUARIO/vercel_saas --token SEU_TOKEN

# Pressione Enter em todas as perguntas (aceitar padrões)
# Ou nomeie o runner: pncp-hetzner
```

#### 2.4. Instalar como Serviço

```bash
# Instalar serviço systemd
sudo ./svc.sh install pncp

# Iniciar serviço
sudo ./svc.sh start

# Verificar status
sudo ./svc.sh status
# Deve mostrar: active (running)
```

#### 2.5. Verificar Runner Online

- Acesse: `https://github.com/SEU_USUARIO/vercel_saas/settings/actions/runners`
- Deve aparecer com status **Idle** (verde)

### 3. 📦 Commit e Push dos Arquivos

Na sua máquina local:

```bash
cd c:\projects\vercel_saas

# Adicionar os novos arquivos
git add .github/workflows/deploy.yml
git add .github/workflows/RUNNER_SETUP.md
git add .github/workflows/DEPLOYMENT_CHECKLIST.md
git add deployment/verify_git_setup.sh

# Commit
git commit -m "feat: Setup self-hosted GitHub Actions runner"

# Push para GitHub
git push origin main
```

### 4. 🎯 Testar o Deploy Automático

1. **Acompanhe o workflow:**
   - Acesse: `https://github.com/SEU_USUARIO/SEU_REPO/actions`
   - Você deve ver o workflow "Deploy PNCP Jobs para Hetzner" executando
   - Status deve ser verde se tudo funcionou

2. **Verifique no servidor:**
   ```bash
   ssh pncp@135.181.44.221
   cd /opt/pncp-jobs
   ls -la
   # Verifique se os arquivos estão atualizados
   ```

3. **Teste manual (opcional):**
   - No GitHub, vá em Actions
   - Selecione "Deploy PNCP Jobs para Hetzner"
   - Clique "Run workflow" → "Run workflow"

### 5. ⏰ Instalação do Cron (Se ainda não foi feito)

No servidor Hetzner:

```bash
# Copiar configuração do cron
sudo cp /opt/pncp-jobs/deployment/pncp-jobs.cron /etc/cron.d/pncp-jobs

# Ajustar permissões
sudo chmod 644 /etc/cron.d/pncp-jobs

# Reiniciar cron
sudo systemctl restart cron

# Verificar
sudo systemctl status cron
```

**Verificar logs do cron:**
```bash
tail -f /var/log/pncp-jobs/pipeline.log
tail -f /var/log/pncp-jobs/emails.log
```

### 6. ✅ Verificação Final

- [ ] GitHub Runner instalado no servidor
- [ ] Runner aparece como "Idle" no GitHub
- [ ] deploy.yml atualizado com `runs-on: self-hosted`
- [ ] Workflow executa sem erros no GitHub Actions
- [ ] Código atualizado no servidor após push
- [ ] Cron jobs instalados e funcionando
- [ ] Logs sendo gerados em `/var/log/pncp-jobs/`
- [ ] rsync instalado no servidor (`sudo apt install rsync`)

## 🚀 Fluxo Normal de Desenvolvimento

Agora, sempre que você fizer mudanças:

```bash
# Na sua máquina local
git add .
git commit -m "Sua mensagem de commit"
git push origin main

# GitHub Actions automaticamente:
# 1. Runner no servidor detecta novo commit
# 2. Faz checkout do código
# 3. Atualiza /opt/pncp-jobs via rsync
# 4. Preserva .env
# 5. Atualiza dependências Python
# 6. Faz health check
# 7. Notifica sucesso/falha
```

## 🆘 Troubleshooting

**Erro: "No runner matching labels: self-hosted"**
- O runner não está online no servidor
- Execute no servidor: `sudo systemctl status actions.runner.*.service`
- Reinicie: `cd /opt/actions-runner && sudo ./svc.sh restart`
- Verifique no GitHub: Settings → Actions → Runners (deve estar verde)

**Erro: "rsync: command not found"**
- Instale rsync no servidor: `sudo apt install -y rsync`

**Erro: "Permission denied"**
- Verifique se o usuário `pncp` é dono do diretório: `ls -la /opt/pncp-jobs`
- Se não for, execute: `sudo chown -R pncp:pncp /opt/pncp-jobs`

**Deploy não executa:**
- Verifique se o runner está "Idle" (verde) no GitHub
- Confirme que o workflow está na branch `main`
- Veja os logs em Actions → Workflow → Logs
- Verifique logs do runner: `sudo journalctl -u actions.runner.*.service -f`

**Runner offline após reboot:**
- Verifique o serviço: `sudo systemctl status actions.runner.*.service`
- Habilite autostart: `sudo systemctl enable actions.runner.*.service`
- Reinicie: `sudo systemctl restart actions.runner.*.service`

## 📚 Documentação

- [GitHub Actions SSH Action](https://github.com/appleboy/ssh-action)
- [HETZNER_SETUP.md](../deployment/HETZNER_SETUP.md) - Setup completo do servidor
- [README.md](../scripts/README.md) - Documentação dos scripts
