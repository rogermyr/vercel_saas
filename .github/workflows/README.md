# GitHub Actions - Deploy Automático

Configuração do deploy automático para o servidor Hetzner usando Self-Hosted Runner.

## 📁 Arquivos

### 🔧 Configuração Principal
- **[deploy.yml](deploy.yml)** - Workflow de deploy (roda automaticamente em push para `main`)

### 📚 Documentação
- **[QUICK_START.md](QUICK_START.md)** - ⚡ **COMECE AQUI** - Setup em 5 minutos
- **[RUNNER_SETUP.md](RUNNER_SETUP.md)** - Guia completo de instalação do runner
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Checklist passo a passo
- **[SECRETS_SETUP.md](SECRETS_SETUP.md)** - Por que não precisa de secrets (self-hosted)

## 🚀 Setup Rápido

### Novo Setup? Comece aqui:

1. **[QUICK_START.md](QUICK_START.md)** - 5 minutos de setup
2. Instale runner no servidor Hetzner
3. Push para GitHub
4. ✅ Deploy automático funcionando!

### Já tem runner? Apenas use:

```bash
git add .
git commit -m "Sua mudança"
git push origin main
# Deploy acontece automaticamente! 🎉
```

## 🏗️ Arquitetura

```
┌─────────────────┐
│  Git Push       │
│  origin main    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GitHub Actions  │
│ (detecta push)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ Self-Hosted Runner          │
│ (no servidor Hetzner)       │
│ /opt/actions-runner         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ 1. Checkout código          │
│ 2. Backup .env              │
│ 3. rsync → /opt/pncp-jobs   │
│ 4. pip install requirements │
│ 5. Health check             │
│ 6. Notificação              │
└─────────────────────────────┘
```

## ✅ Vantagens do Self-Hosted Runner

### vs SSH Action (método anterior)

| Aspecto | SSH Action | Self-Hosted Runner |
|---------|------------|-------------------|
| **Configuração** | 3 GitHub Secrets | Setup único no servidor |
| **Firewall** | ❌ Bloqueado | ✅ Sem problemas |
| **Velocidade** | Lento (rede) | ⚡ Instantâneo |
| **Timeout** | Comum | ✅ Nunca |
| **Segurança** | Chave no GitHub | ✅ Local |
| **Manutenção** | Chaves SSH | ✅ Zero |

## 📊 Status do Runner

Verificar se runner está online:
- GitHub → Settings → Actions → Runners
- Deve aparecer: **pncp-hetzner** com status **Idle** 🟢

## 🔍 Monitoramento

```bash
# Ver status do runner
sudo systemctl status actions.runner.*.service

# Ver logs em tempo real
sudo journalctl -u actions.runner.*.service -f

# Ver logs de deploy
tail -f /var/log/pncp-jobs/*.log

# Ver processos
ps aux | grep Runner.Listener
```

## 🆘 Troubleshooting

| Sintoma | Causa | Solução |
|---------|-------|---------|
| Workflow não inicia | Runner offline | `sudo systemctl restart actions.runner.*.service` |
| "No runner matching labels" | Runner não encontrado | Verificar status no GitHub Settings |
| "rsync: command not found" | rsync não instalado | `sudo apt install -y rsync` |
| "Permission denied" | Permissões incorretas | `sudo chown -R pncp:pncp /opt/pncp-jobs` |
| Runner offline após reboot | Serviço não autostart | `sudo systemctl enable actions.runner.*.service` |

## 🔧 Comandos Úteis

```bash
# No servidor Hetzner
cd /opt/actions-runner

# Status
sudo ./svc.sh status

# Reiniciar
sudo ./svc.sh restart

# Parar
sudo ./svc.sh stop

# Ver configuração
cat .runner

# Ver logs
ls -la _diag/
```

## 📝 Fluxo de Deploy

1. **Developer** faz `git push origin main`
2. **GitHub** detecta o push
3. **Runner** no servidor Hetzner pega o job
4. **Workflow** executa:
   - Checkout do código
   - Backup do `.env`
   - rsync para `/opt/pncp-jobs`
   - Instala dependências
   - Health check
5. **Notificação** de sucesso/falha

## 🎯 Próximos Passos

- [ ] Setup inicial? → [QUICK_START.md](QUICK_START.md)
- [ ] Já tem runner? → Apenas faça `git push`!
- [ ] Problemas? → Veja Troubleshooting acima
- [ ] Quer saber mais? → [RUNNER_SETUP.md](RUNNER_SETUP.md)

## 📚 Documentação Adicional

- **Servidor**: [../../deployment/HETZNER_SETUP.md](../../deployment/HETZNER_SETUP.md)
- **Scripts**: [../../scripts/README.md](../../scripts/README.md)
- **Cron Jobs**: [../../deployment/pncp-jobs.cron](../../deployment/pncp-jobs.cron)

---

## 🔐 Segurança

- ✅ Runner roda como usuário `pncp` (não root)
- ✅ Sem chaves SSH no GitHub
- ✅ Deploy local (sem exposição externa)
- ✅ `.env` preservado automaticamente
- ✅ Logs auditáveis

## 📞 Suporte

**Logs do Runner:**
```bash
sudo journalctl -u actions.runner.*.service --since "1 hour ago"
```

**Logs do Deploy:**
```bash
tail -100 /var/log/pncp-jobs/pipeline.log
```

**Status dos Jobs Agendados:**
```bash
sudo grep CRON /var/log/syslog | grep pncp-jobs | tail -20
```

---

**Deploy automático está funcionando! 🚀**
