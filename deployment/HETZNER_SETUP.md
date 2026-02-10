# Guia de Implantação - PNCP Jobs no Hetzner

Guia completo para configurar e hospedar os jobs agendados do sistema PNCP em um servidor Hetzner VPS.

## 📋 Índice

1. [Requisitos](#requisitos)
2. [Criação do Servidor Hetzner](#criação-do-servidor-hetzner)
3. [Configuração Inicial do Servidor](#configuração-inicial-do-servidor)
4. [Instalação de Dependências](#instalação-de-dependências)
5. [Deploy da Aplicação](#deploy-da-aplicação)
6. [Configuração dos Cron Jobs](#configuração-dos-cron-jobs)
7. [Deploy Automático com GitHub Actions](#deploy-automático-com-github-actions)
8. [Monitoramento e Logs](#monitoramento-e-logs)
9. [Manutenção](#manutenção)
10. [Troubleshooting](#troubleshooting)

---

## 1. Requisitos

### Requisitos no Hetzner

- **Servidor VPS**: CX21 ou superior (2 vCPU, 4GB RAM, 40GB SSD)
- **Sistema Operacional**: Ubuntu 22.04 LTS
- **Custo estimado**: ~€5-10/mês

### Requisitos Locais

- Acesso SSH configurado
- Git instalado localmente
- Conta Hetzner Cloud ativa

---

## 2. Criação do Servidor Hetzner

### 2.1 Criar VPS via Hetzner Cloud Console

1. Acesse https://console.hetzner.cloud/
2. Clique em **"New Project"** → Nome: `pncp-jobs`
3. Clique em **"Add Server"**
4. Configurações:
   - **Location**: Nuremberg, Germany (ou mais próximo)
   - **Image**: Ubuntu 22.04
   - **Type**: CX21 (2 vCPU, 4GB RAM)
   - **Networking**: IPv4 público
   - **SSH Keys**: Adicione sua chave pública SSH
   - **Name**: `pncp-jobs-prod`
5. Clique em **"Create & Buy Now"**

### 2.2 Configurar Firewall (Opcional mas Recomendado)

```bash
# No console Hetzner, criar firewall:
# - Regra 1: Allow SSH (22/tcp) de qualquer IP
# - Regra 2: Allow ICMP (ping)
# - Aplicar ao servidor pncp-jobs-prod
```

### 2.3 Conectar ao Servidor

```bash
# Obter IP do servidor no console Hetzner
ssh root@<IP_DO_SERVIDOR>
```

---

## 3. Configuração Inicial do Servidor

### 3.1 Atualizar Sistema

```bash
apt update && apt upgrade -y
```

### 3.2 Configurar Timezone

```bash
timedatectl set-timezone America/Sao_Paulo
```

### 3.3 Criar Usuário Não-Root

```bash
# Criar usuário pncp
useradd -m -s /bin/bash -d /opt/pncp-jobs pncp

# Adicionar ao grupo sudo (opcional, para manutenção)
usermod -aG sudo pncp

# Configurar senha (opcional)
passwd pncp
```

### 3.4 Configurar SSH para Usuário pncp

```bash
# Copiar chaves SSH do root para pncp
mkdir -p /opt/pncp-jobs/.ssh
cp /root/.ssh/authorized_keys /opt/pncp-jobs/.ssh/
chown -R pncp:pncp /opt/pncp-jobs/.ssh
chmod 700 /opt/pncp-jobs/.ssh
chmod 600 /opt/pncp-jobs/.ssh/authorized_keys

# Testar conexão (em nova janela terminal)
# ssh pncp@<IP_DO_SERVIDOR>
```

---

## 4. Instalação de Dependências

### 4.1 Instalar Pacotes do Sistema

```bash
# Como root
apt install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    postgresql-client \
    curl \
    wget \
    vim \
    htop \
    supervisor \
    build-essential \
    libpq-dev
```

### 4.2 Verificar Instalação

```bash
python3.11 --version  # Deve mostrar Python 3.11.x
git --version
psql --version
```

---

## 5. Deploy da Aplicação

### 5.1 Clonar Repositório

```bash
# Como usuário pncp
su - pncp
cd /opt/pncp-jobs

# Clonar repositório (ajuste a URL conforme seu repositório)
git clone https://github.com/seu-usuario/vercel_saas.git .

# OU se preferir, fazer upload via SCP/SFTP dos arquivos locais
```

### 5.2 Alternativa: Upload Manual via SCP

Se preferir fazer upload dos arquivos locais:

```bash
# No seu computador local (Windows/PowerShell)
cd c:\projects\vercel_saas
scp -r * pncp@<IP_DO_SERVIDOR>:/opt/pncp-jobs/
```

### 5.3 Criar Virtual Environment

```bash
# Como usuário pncp
cd /opt/pncp-jobs
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### 5.4 Instalar Dependências Python

```bash
# Com venv ativado
pip install -r requirements.txt
```

### 5.5 Configurar Variáveis de Ambiente

```bash
# Criar arquivo .env
cd /opt/pncp-jobs
nano .env
```

Copie o conteúdo do seu `.env` local. Exemplo:

```env
# Database
DATABASE_URL=postgresql://usuario:senha@135.181.44.221:5432/pncp_db

# Email Configuration (Mailtrap para testes)
MAIL_SERVER=sandbox.smtp.mailtrap.io
MAIL_PORT=2525
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=seu_usuario_mailtrap
MAIL_PASSWORD=sua_senha_mailtrap
MAIL_DEFAULT_SENDER=noreply@pncp.com

# Aplicação
SECRET_KEY=sua_chave_secreta_aqui
CRON_SECRET=sua_chave_cron_aqui

# NÃO definir VERCEL=1 (removemos essas limitações)
```

**Importante**: Salve com `Ctrl+O`, `Enter`, `Ctrl+X`

### 5.6 Configurar Permissões

```bash
chmod 600 /opt/pncp-jobs/.env
chown pncp:pncp /opt/pncp-jobs/.env
```

### 5.7 Testar Conexão com Banco de Dados

```bash
# Testar conexão PostgreSQL
psql "postgresql://usuario:senha@135.181.44.221:5432/pncp_db" -c "SELECT 1;"
```

---

## 6. Configuração dos Cron Jobs

### 6.1 Criar Diretório de Logs

```bash
# Como root
sudo mkdir -p /var/log/pncp-jobs
sudo chown pncp:pncp /var/log/pncp-jobs
sudo chmod 755 /var/log/pncp-jobs
```

### 6.2 Instalar Arquivo Cron

```bash
# Como root
sudo cp /opt/pncp-jobs/deployment/pncp-jobs.cron /etc/cron.d/pncp-jobs
sudo chmod 644 /etc/cron.d/pncp-jobs
sudo chown root:root /etc/cron.d/pncp-jobs
```

### 6.3 Editar Email de Notificações

```bash
# Editar o arquivo cron para configurar seu email
sudo nano /etc/cron.d/pncp-jobs

# Alterar a linha:
MAILTO=seu-email@exemplo.com
```

### 6.4 Verificar Sintaxe Cron

```bash
# Verificar se o cron foi carregado
sudo systemctl restart cron
sudo systemctl status cron

# Verificar se o arquivo está listado
ls -la /etc/cron.d/pncp-jobs
```

### 6.5 Configurar Logrotate

```bash
# Como root
sudo cp /opt/pncp-jobs/deployment/pncp-logrotate.conf /etc/logrotate.d/pncp-jobs
sudo chmod 644 /etc/logrotate.d/pncp-jobs

# Testar configuração
sudo logrotate -d /etc/logrotate.d/pncp-jobs
```

---

## 7. Deploy Automático com GitHub Actions

### 7.1 Configurar Git no Servidor

O deploy automático usa Git para atualizar o código. Configure isso primeiro:

```bash
# Como usuário pncp
su - pncp
cd /opt/pncp-jobs

# Verificar se Git está configurado
bash deployment/verify_git_setup.sh
```

**Se Git não estiver configurado:**

```bash
# Inicializar repositório
git init
git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
git branch -M main
git fetch origin
git reset --hard origin/main

# Restaurar .env se necessário
# (git reset sobrescreve arquivos locais)
```

### 7.2 Configurar Autenticação SSH do Servidor com GitHub

Para que o `git pull` funcione automaticamente, configure SSH keys:

```bash
# Como usuário pncp
ssh-keygen -t ed25519 -C "pncp@hetzner"
# Aperte Enter 3 vezes (sem senha)

# Copiar chave pública
cat ~/.ssh/id_ed25519.pub
```

**Adicione a chave no GitHub:**
1. Acesse https://github.com/settings/keys
2. "New SSH key" → Cole a chave
3. Título: "Hetzner PNCP Server"

**Testar conexão:**
```bash
ssh -T git@github.com
# Retorno esperado: "Hi username! You've successfully authenticated..."
```

### 7.3 Configurar GitHub Secrets

No repositório GitHub, configure 3 secrets:

1. **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

2. Adicione:
   - `HETZNER_HOST`: IP do servidor (ex: `135.181.44.221`)
   - `HETZNER_USERNAME`: usuário SSH (ex: `pncp`)
   - `HETZNER_SSH_KEY`: sua chave privada SSH completa (da sua máquina local, não do servidor)

### 7.4 Como Funciona

Agora, sempre que você der `git push origin main`:

1. GitHub Actions detecta o push
2. Conecta no servidor via SSH
3. Executa `git pull origin main`
4. Preserva o arquivo `.env`
5. Atualiza dependências: `pip install -r requirements.txt`
6. Executa health check do banco
7. Notifica sucesso/falha

### 7.5 Executar Deploy Manual

Você também pode executar o deploy manualmente:

1. Acesse GitHub → **Actions**
2. Selecione "Deploy PNCP Jobs para Hetzner"
3. Clique **"Run workflow"**

### 7.6 Monitorar Deploys

- **Logs do GitHub Actions**: Repositório → Actions → Workflow → View logs
- **Verificar no servidor**:
  ```bash
  ssh pncp@135.181.44.221
  cd /opt/pncp-jobs
  git log -1 --oneline  # Ver último commit
  ```

**Documentação completa**: Veja `.github/workflows/DEPLOYMENT_CHECKLIST.md`

---

## 8. Monitoramento e Logs

### 7.1 Testar Jobs Manualmente

```bash
# Como usuário pncp
su - pncp
cd /opt/pncp-jobs
source venv/bin/activate

# Testar cada job individualmente
python scripts/run_crawler.py
python scripts/run_items.py
python scripts/run_silver.py
python scripts/run_emails.py
```

### 7.2 Monitorar Logs em Tempo Real

```bash
# Ver todos os logs
tail -f /var/log/pncp-jobs/*.log

# Ver log específico
tail -f /var/log/pncp-jobs/crawler.log

# Ver últimas 100 linhas
tail -n 100 /var/log/pncp-jobs/silver.log

# Ver erros no syslog
sudo grep CRON /var/log/syslog | tail -20
```

### 7.3 Verificar Execuções do Cron

```bash
# Ver últimas execuções
sudo grep CRON /var/log/syslog | grep pncp-jobs

# Ver cron jobs do usuário pncp
sudo crontab -l -u pncp

# Verificar se cron está rodando
sudo systemctl status cron
```

### 7.4 Comandos Úteis de Monitoramento

```bash
# Ver processos Python em execução
ps aux | grep python

# Ver uso de CPU e memória
htop

# Ver uso de disco
df -h

# Ver espaço usado pelos logs
du -sh /var/log/pncp-jobs/

# Verificar conectividade com PostgreSQL
psql "postgresql://usuario:senha@135.181.44.221:5432/pncp_db" -c "SELECT COUNT(*) FROM bronze_pncp_licitacoes;"
```

---

## 9. Manutenção

### 9.1 Atualização do Código

```bash
# Como usuário pncp
su - pncp
cd /opt/pncp-jobs

# Backup do .env (caso seja sobrescrito)
cp .env .env.backup

# Atualizar via git
git pull origin main

# OU upload manual via SCP

# Reinstalar dependências se necessário
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Restaurar .env se necessário
mv .env.backup .env
```

### 8.2 Limpar Logs Antigos Manualmente

```bash
# Remover logs com mais de 30 dias
find /var/log/pncp-jobs/ -name "*.log*" -mtime +30 -delete

# Limpar logs grandes imediatamente
truncate -s 0 /var/log/pncp-jobs/crawler.log
```

### 8.3 Backup do .env

```bash
# Criar backup
sudo cp /opt/pncp-jobs/.env /root/pncp-env-backup-$(date +%Y%m%d).env
sudo chmod 600 /root/pncp-env-backup-*.env
```

### 8.4 Reiniciar Jobs

```bash
# Forçar execução de um job (não esperar o cron)
sudo -u pncp /opt/pncp-jobs/venv/bin/python /opt/pncp-jobs/scripts/run_crawler.py

# Ou como usuário pncp
su - pncp
cd /opt/pncp-jobs
source venv/bin/activate
python scripts/run_crawler.py
```

---

## 10. Troubleshooting

### 10.1 Cron não está executando

```bash
# Verificar serviço cron
sudo systemctl status cron
sudo systemctl restart cron

# Verificar permissões do arquivo cron
ls -la /etc/cron.d/pncp-jobs
# Deve ser: -rw-r--r-- root root

# Verificar sintaxe do arquivo
cat /etc/cron.d/pncp-jobs

# Verificar syslog
sudo tail -100 /var/log/syslog | grep CRON
```

### 10.2 Erro de Importação Python

```bash
# Verificar se o venv está correto
/opt/pncp-jobs/venv/bin/python --version

# Reinstalar dependências
cd /opt/pncp-jobs
source venv/bin/activate
pip install -r requirements.txt --force-reinstall
```

### 10.3 Erro de Conexão com Banco de Dados

```bash
# Testar conexão direta
psql "postgresql://usuario:senha@135.181.44.221:5432/pncp_db" -c "SELECT 1;"

# Verificar .env
cat /opt/pncp-jobs/.env | grep DATABASE_URL

# Testar conectividade de rede
ping 135.181.44.221
telnet 135.181.44.221 5432
```

### 10.4 Permissões Negadas

```bash
# Corrigir permissões do diretório
sudo chown -R pncp:pncp /opt/pncp-jobs
sudo chmod -R 755 /opt/pncp-jobs
sudo chmod 600 /opt/pncp-jobs/.env

# Corrigir permissões dos logs
sudo chown -R pncp:pncp /var/log/pncp-jobs
sudo chmod 755 /var/log/pncp-jobs
```

### 10.5 Job Travou / Não Termina

```bash
# Encontrar processo
ps aux | grep python | grep scripts

# Matar processo (substituir PID)
kill -9 <PID>

# Ver jobs em execução
pgrep -f "run_crawler.py"
```

### 10.6 Logs Muito Grandes

```bash
# Ver tamanho dos logs
du -sh /var/log/pncp-jobs/*

# Limpar log específico
truncate -s 0 /var/log/pncp-jobs/crawler.log

# Forçar rotação de logs
sudo logrotate -f /etc/logrotate.d/pncp-jobs
```

---

## 🎯 Checklist Final

- [ ] Servidor Hetzner criado e conectado via SSH
- [ ] Sistema atualizado e timezone configurado
- [ ] Usuário `pncp` criado e configurado
- [ ] Python 3.11 e dependências instaladas
- [ ] Código clonado/enviado para `/opt/pncp-jobs`
- [ ] Virtual environment criado e dependências instaladas
- [ ] Arquivo `.env` configurado e com permissões 600
- [ ] Conexão com PostgreSQL testada
- [ ] Diretório `/var/log/pncp-jobs` criado
- [ ] Arquivo cron instalado em `/etc/cron.d/pncp-jobs`
- [ ] Email de notificações cron configurado
- [ ] Logrotate configurado
- [ ] Jobs testados manualmente e executando sem erros
- [ ] Logs sendo gravados corretamente
- [ ] Cron executando jobs nos horários agendados

---

## 📞 Próximos Passos

1. **Aguardar primeira execução automática** (próximo dia às 3:00 AM)
2. **Monitorar logs** nas primeiras 24-48h
3. **Validar dados no banco** após execuções
4. **Configurar SMTP produção** (substituir Mailtrap)
5. **Configurar monitoramento** (opcional: UptimeRobot, Healthchecks.io)
6. **Documentar senhas e acessos** em gerenciador seguro

---

## 📚 Recursos Adicionais

- [Documentação Hetzner Cloud](https://docs.hetzner.com/cloud/)
- [Cron HowTo Ubuntu](https://help.ubuntu.com/community/CronHowto)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Python Virtual Environments](https://docs.python.org/3/library/venv.html)

---

**Última atualização**: 2026-02-09
