# Setup GitHub Self-Hosted Runner no Hetzner

Este guia configura um GitHub Actions Runner diretamente no servidor Hetzner, eliminando a necessidade de conexão SSH externa e problemas de firewall.

## 🎯 Por que Self-Hosted Runner?

- ✅ Elimina problemas de timeout/firewall
- ✅ Roda localmente no servidor
- ✅ Deploy mais rápido (sem latência de rede)
- ✅ Acesso direto aos recursos do servidor
- ✅ Não precisa de secrets SSH

## 📋 Passo a Passo

### 1. Conectar no Servidor

```bash
ssh pncp@135.181.44.221
```

### 2. Criar Diretório do Runner

```bash
# Criar e configurar diretório
sudo mkdir -p /opt/actions-runner
sudo chown pncp:pncp /opt/actions-runner
cd /opt/actions-runner
```

### 3. Baixar GitHub Actions Runner

```bash
# Baixar versão mais recente
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz

# Extrair
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# Limpar arquivo
rm actions-runner-linux-x64-2.311.0.tar.gz
```

### 4. Obter Token de Configuração (NO NAVEGADOR)

1. Abra: `https://github.com/SEU_USUARIO/vercel_saas/settings/actions/runners/new`
   - Substitua `SEU_USUARIO` pelo seu usuário GitHub

2. Selecione: **Linux** → **x64**

3. Copie o comando `./config.sh` que aparece, algo como:
   ```bash
   ./config.sh --url https://github.com/USUARIO/vercel_saas --token ABCD1234TOKEN
   ```

### 5. Configurar Runner (NO SERVIDOR)

```bash
# Cole o comando copiado do passo 4
./config.sh --url https://github.com/USUARIO/vercel_saas --token SEU_TOKEN_AQUI

# Quando perguntar, responda:
# Enter the name of the runner group: [pressione Enter]
# Enter the name of runner: pncp-hetzner [ou pressione Enter]
# Enter any additional labels: [pressione Enter]
# Enter name of work folder: [pressione Enter]
```

**Saída esperada:**
```
✓ Runner successfully added
✓ Runner connection is good
```

### 6. Instalar como Serviço (Roda Sempre)

```bash
# Instalar serviço systemd
sudo ./svc.sh install pncp

# Iniciar serviço
sudo ./svc.sh start

# Verificar status
sudo ./svc.sh status
```

**Saída esperada:**
```
● actions.runner.USUARIO-vercel_saas.pncp-hetzner.service - GitHub Actions Runner
     Active: active (running)
```

### 7. Verificar Runner Online

1. Abra: `https://github.com/SEU_USUARIO/vercel_saas/settings/actions/runners`
2. Você deve ver: **pncp-hetzner** com status **Idle** (verde)

## ✅ Testar Deploy

```bash
# No seu PC, commit e push
git add .github/workflows/deploy.yml
git commit -m "feat: Configure self-hosted runner"
git push origin main

# Monitorar execução
# GitHub → Actions → Veja o workflow rodando
```

## 🔍 Comandos Úteis

```bash
# Ver status do runner
sudo systemctl status actions.runner.*.service

# Ver logs do runner
sudo journalctl -u actions.runner.*.service -f

# Parar runner
sudo ./svc.sh stop

# Reiniciar runner
sudo ./svc.sh restart

# Desinstalar runner
sudo ./svc.sh uninstall
./config.sh remove --token SEU_TOKEN
```

## 🔧 Troubleshooting

### Runner não aparece no GitHub

```bash
# Verificar se está rodando
ps aux | grep Runner.Listener

# Ver logs
cd /opt/actions-runner
cat _diag/Runner_*.log
```

### Erro "Must not run with sudo"

```bash
# Runner deve rodar como usuário pncp
sudo su - pncp
cd /opt/actions-runner
./config.sh ...
```

### Deploy falha com "rsync: command not found"

```bash
# Instalar rsync
sudo apt update
sudo apt install -y rsync
```

### Workflow não encontra self-hosted runner

1. Verifique se runner está **Idle** (verde) no GitHub
2. Verifique se deploy.yml tem `runs-on: self-hosted`
3. Reinicie o serviço: `sudo ./svc.sh restart`

## 🔄 Atualizar Runner

```bash
cd /opt/actions-runner

# Parar serviço
sudo ./svc.sh stop

# Baixar nova versão
curl -o actions-runner-linux-x64-2.XXX.0.tar.gz -L https://github.com/actions/runner/releases/download/vX.XXX.0/actions-runner-linux-x64-2.XXX.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.XXX.0.tar.gz

# Reiniciar
sudo ./svc.sh start
```

## 📊 Gerenciar Múltiplos Runners (Opcional)

Se quiser adicionar mais runners (ex: staging, production):

```bash
# Criar outro diretório
sudo mkdir -p /opt/actions-runner-staging
sudo chown pncp:pncp /opt/actions-runner-staging
cd /opt/actions-runner-staging

# Repetir processo com outro token e nome
# Use labels para diferenciar:
# ./config.sh ... --labels production
# ./config.sh ... --labels staging
```

No workflow:
```yaml
runs-on: [self-hosted, production]  # Usa runner específico
```

## 🛡️ Segurança

- Runner roda como usuário `pncp` (não root)
- Tem acesso total ao servidor (necessário)
- Workflows podem executar comandos sudo se usuário tiver permissão
- Recomendado: usar runner apenas em repositórios privados
- Token expira após 1 hora (só para configuração)

## 📚 Documentação Oficial

- [GitHub Self-Hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [Runner Releases](https://github.com/actions/runner/releases)
- [Security Hardening](https://docs.github.com/en/actions/security-guides)

---

**Instalação completa! Agora todo push na branch `main` vai fazer deploy automaticamente no servidor Hetzner.**
