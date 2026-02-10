# Checklist de Deploy Automático - GitHub Actions → Hetzner

Use este checklist para configurar o deploy automático do PNCP Jobs.

## 📋 Checklist de Configuração

### 1. ✅ Arquivos Criados (Já Concluído)
- [x] `.github/workflows/deploy.yml` - workflow de deploy
- [x] `.github/workflows/SECRETS_SETUP.md` - guia de configuração
- [x] `deployment/verify_git_setup.sh` - script de verificação

### 2. 🔧 Configuração no Servidor Hetzner

#### 2.1. Conecte-se ao servidor
```bash
ssh pncp@135.181.44.221
```

#### 2.2. Navegue até o diretório
```bash
cd /opt/pncp-jobs
```

#### 2.3. Verifique se o Git está inicializado
```bash
bash deployment/verify_git_setup.sh
```

**Se o Git NÃO estiver configurado:**

**Opção A: Clone do zero (RECOMENDADO se você tem o repo no GitHub)**
```bash
# Saia do diretório
cd /opt

# Faça backup do código atual
mv pncp-jobs pncp-jobs.backup

# Clone o repositório
git clone https://github.com/SEU_USUARIO/SEU_REPO.git pncp-jobs

# Entre no diretório
cd pncp-jobs

# Restaure o .env
cp /opt/pncp-jobs.backup/.env .env

# Recrie o virtualenv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Opção B: Inicializar Git no diretório atual**
```bash
cd /opt/pncp-jobs

# Inicializar git
git init

# Adicionar remote
git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git

# Configurar branch main
git branch -M main

# Fazer fetch
git fetch origin

# Resetar para o estado do repositório (CUIDADO: isso sobrescreve arquivos locais)
# Faça backup do .env antes!
cp .env .env.backup
git reset --hard origin/main
mv .env.backup .env
```

#### 2.4. Configure autenticação SSH do servidor com GitHub

**Para que o git pull funcione, o servidor precisa autenticar com GitHub:**

```bash
# No servidor Hetzner, como usuário pncp
ssh-keygen -t ed25519 -C "pncp@hetzner"
# Aperte Enter 3 vezes (sem senha)

# Copie a chave pública
cat ~/.ssh/id_ed25519.pub
```

Agora adicione esta chave no GitHub:
1. Acesse: https://github.com/settings/keys
2. Clique em "New SSH key"
3. Cole a chave copiada
4. Título: "Hetzner PNCP Server"
5. Salve

**Teste a conexão:**
```bash
ssh -T git@github.com
# Deve retornar: "Hi username! You've successfully authenticated..."
```

### 3. 🔐 Configuração dos GitHub Secrets

No GitHub (na sua máquina local):

1. Acesse: `https://github.com/SEU_USUARIO/SEU_REPO/settings/secrets/actions`

2. Adicione os 3 secrets:

   **HETZNER_HOST**
   ```
   135.181.44.221
   ```

   **HETZNER_USERNAME**
   ```
   pncp
   ```

   **HETZNER_SSH_KEY**
   - Na sua máquina local, copie o conteúdo da sua chave privada:
     ```bash
     # Windows WSL ou Linux
     cat ~/.ssh/id_rsa
     
     # Ou se você usa outra chave
     cat ~/.ssh/id_ed25519
     ```
   - Cole TODO o conteúdo (incluindo `-----BEGIN ... KEY-----` e `-----END ... KEY-----`)

### 4. 📦 Commit e Push dos Arquivos

Na sua máquina local:

```bash
cd c:\projects\vercel_saas

# Adicionar os novos arquivos
git add .github/workflows/deploy.yml
git add .github/workflows/SECRETS_SETUP.md
git add .github/workflows/DEPLOYMENT_CHECKLIST.md
git add deployment/verify_git_setup.sh

# Commit
git commit -m "feat: Add GitHub Actions auto-deploy to Hetzner"

# Push para GitHub
git push origin main
```

### 5. 🎯 Testar o Deploy Automático

1. **Acompanhe o workflow:**
   - Acesse: `https://github.com/SEU_USUARIO/SEU_REPO/actions`
   - Você deve ver o workflow "Deploy PNCP Jobs para Hetzner" executando

2. **Verifique no servidor:**
   ```bash
   ssh pncp@135.181.44.221
   cd /opt/pncp-jobs
   git log -1 --oneline
   # Deve mostrar seu último commit
   ```

3. **Teste manual (opcional):**
   - No GitHub, vá em Actions
   - Selecione "Deploy PNCP Jobs para Hetzner"
   - Clique "Run workflow"

### 6. ⏰ Instalação do Cron (Se ainda não foi feito)

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

### 7. ✅ Verificação Final

- [ ] Git configurado no servidor (`git pull` funciona)
- [ ] SSH keys configuradas (servidor → GitHub)
- [ ] 3 GitHub Secrets configurados corretamente
- [ ] Workflow executa sem erros no GitHub Actions
- [ ] Código atualizado no servidor após push
- [ ] Cron jobs instalados e funcionando
- [ ] Logs sendo gerados em `/var/log/pncp-jobs/`

## 🚀 Fluxo Normal de Desenvolvimento

Agora, sempre que você fizer mudanças:

```bash
# Na sua máquina local
git add .
git commit -m "Sua mensagem de commit"
git push origin main

# GitHub Actions automaticamente:
# 1. Conecta no servidor
# 2. Faz git pull
# 3. Atualiza dependências
# 4. Faz health check
# 5. Notifica sucesso/falha
```

## 🆘 Troubleshooting

**Erro: "git pull failed"**
- Execute `bash deployment/verify_git_setup.sh` no servidor
- Verifique se a chave SSH do servidor está no GitHub

**Erro: "Permission denied"**
- Verifique se o usuário `pncp` é dono do diretório: `ls -la /opt/pncp-jobs`
- Se não for, execute: `sudo chown -R pncp:pncp /opt/pncp-jobs`

**Erro: "Host key verification failed"**
- No servidor, execute: `ssh -T git@github.com` e aceite o fingerprint

**Deploy não executa:**
- Verifique se os secrets estão configurados corretamente
- Confirme que o workflow está na branch `main`
- Veja os logs em Actions → Workflow → Logs

## 📚 Documentação

- [GitHub Actions SSH Action](https://github.com/appleboy/ssh-action)
- [HETZNER_SETUP.md](../deployment/HETZNER_SETUP.md) - Setup completo do servidor
- [README.md](../scripts/README.md) - Documentação dos scripts
