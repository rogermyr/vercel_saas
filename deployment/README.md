# Deployment - Arquivos de Configuração do Servidor

Esta pasta contém arquivos de configuração para deploy no servidor Hetzner.

## 📁 Arquivos

### `HETZNER_SETUP.md`
Guia completo passo-a-passo para configurar o servidor Hetzner do zero.

**Inclui:**
- Criação do VPS Hetzner
- Configuração inicial do Ubuntu
- Instalação de dependências
- Deploy da aplicação
- Configuração de cron jobs
- Monitoramento e troubleshooting

### `pncp-jobs.cron`
Arquivo de configuração do cron com todos os jobs agendados.

**Uso:**
```bash
sudo cp pncp-jobs.cron /etc/cron.d/pncp-jobs
sudo chmod 644 /etc/cron.d/pncp-jobs
```

**Jobs configurados:**
- Crawler: 3:00 AM
- Item Collector: 3:30 AM
- Silver Processor: 5:00 AM
- Email Notifications: 9:00 AM

### `pncp-logrotate.conf`
Configuração de rotação automática de logs.

**Uso:**
```bash
sudo cp pncp-logrotate.conf /etc/logrotate.d/pncp-jobs
sudo chmod 644 /etc/logrotate.d/pncp-jobs
```

**Configuração:**
- Rotação diária
- Mantém últimos 30 dias
- Compressão automática
- Logs comprimidos com data no nome

## 🚀 Quick Start

1. **Leia o guia completo:**
   ```bash
   cat HETZNER_SETUP.md
   ```

2. **Siga os passos na ordem:**
   - Criar servidor
   - Configurar sistema
   - Instalar dependências
   - Deploy da aplicação
   - Configurar cron

3. **Testar jobs:**
   ```bash
   python scripts/run_crawler.py
   ```

4. **Monitorar:**
   ```bash
   tail -f /var/log/pncp-jobs/*.log
   ```

## 📋 Checklist Rápido

- [ ] Servidor Hetzner criado
- [ ] SSH configurado
- [ ] Usuário `pncp` criado
- [ ] Python 3.11 instalado
- [ ] Código deployed em `/opt/pncp-jobs`
- [ ] `.env` configurado
- [ ] Cron instalado (`/etc/cron.d/pncp-jobs`)
- [ ] Logrotate instalado (`/etc/logrotate.d/pncp-jobs`)
- [ ] Jobs testados manualmente
- [ ] Logs monitorados

## 🔗 Arquivos Relacionados

- [`../scripts/`](../scripts/) - Scripts Python dos jobs
- [`../.env`](../.env) - Variáveis de ambiente (copiar para servidor)
- [`../requirements.txt`](../requirements.txt) - Dependências Python

---

**Importante:** Sempre faça backup do arquivo `.env` antes de fazer deploy!
