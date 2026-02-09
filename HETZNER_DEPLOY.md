# Deploy PNCP Jobs no Hetzner - Resumo de Implementação

Este projeto foi otimizado para rodar jobs agendados em um servidor dedicado Hetzner.

## ✅ O Que Foi Feito

### 1. **Código Otimizado para Servidor Dedicado**

Removidas todas as limitações do Vercel:

- ✅ **Connection Pools**: Aumentados de 2-5 para 10 (pool_size) e 20 (max_overflow)
- ✅ **Batch Sizes**: Aumentados significativamente
  - Item collector: 20 → 500
  - Silver processor: Sem limites de batches
- ✅ **Email**: Removido limite de 50 emails por execução
- ✅ **Timeouts**: Removidos todos os checks `os.getenv("VERCEL")`

**Arquivos modificados:**
- [api/models.py](api/models.py) - Connection pool otimizado
- [api/notification_service.py](api/notification_service.py) - Connection pool otimizado
- [api/item_collector.py](api/item_collector.py) - Batch size 500, sem checks Vercel
- [api/silver_processor.py](api/silver_processor.py) - Sem limites de processamento
- [app.py](app.py) - Sem limite de emails

### 2. **Scripts Wrapper Criados**

4 scripts Python prontos para execução via cron em [`scripts/`](scripts/):

- ✅ **run_crawler.py** - Coleta licitações do PNCP
- ✅ **run_items.py** - Coleta itens das licitações
- ✅ **run_silver.py** - Processa dados Bronze → Silver
- ✅ **run_emails.py** - Envia notificações por email

**Recursos:**
- Logging completo em `/var/log/pncp-jobs/`
- Tratamento de erros robusto
- Códigos de saída (0=sucesso, 1=erro)
- Timestamps e duração de execução

### 3. **Configuração de Cron**

Arquivo pronto em [`deployment/pncp-jobs.cron`](deployment/pncp-jobs.cron):

```
0 3 * * *   - Crawler (3:00 AM)
30 3 * * *  - Item Collector (3:30 AM)
0 5 * * *   - Silver Processor (5:00 AM)
0 9 * * *   - Email Notifications (9:00 AM)
```

Inclui:
- Configuração de MAILTO para alertas
- Redirecionamento de logs
- Documentação inline completa

### 4. **Rotação de Logs**

Configuração logrotate em [`deployment/pncp-logrotate.conf`](deployment/pncp-logrotate.conf):

- Rotação diária
- Mantém últimos 30 dias
- Compressão automática
- Permissões corretas

### 5. **Script de Health Check**

Monitoramento em [`scripts/health_check.sh`](scripts/health_check.sh):

Verifica:
- ✅ Atualização dos logs (últimas 24h)
- ✅ Erros recentes nos logs
- ✅ Tamanho dos logs (alerta se > 500MB)
- ✅ Processos Python em execução
- ✅ Configuração do cron
- ✅ Conectividade com PostgreSQL
- ✅ Espaço em disco (alerta se > 85%)
- ✅ Uso de memória (alerta se > 90%)

### 6. **Documentação Completa**

Guia detalhado em [`deployment/HETZNER_SETUP.md`](deployment/HETZNER_SETUP.md):

Passo-a-passo completo incluindo:
- Criação do VPS Hetzner
- Configuração inicial Ubuntu 22.04
- Instalação de dependências
- Deploy da aplicação
- Configuração de cron e logs
- Monitoramento e troubleshooting
- Comandos úteis de manutenção

## 🚀 Como Usar

### Quick Start (3 passos)

1. **Leia o guia completo:**
   ```bash
   cat deployment/HETZNER_SETUP.md
   ```

2. **Crie servidor Hetzner e execute setup:**
   - Siga cada seção do HETZNER_SETUP.md na ordem
   - Configure .env no servidor
   - Instale cron e logrotate

3. **Teste e monitore:**
   ```bash
   # Teste manual
   python scripts/run_crawler.py
   
   # Monitore logs
   tail -f /var/log/pncp-jobs/*.log
   
   # Health check
   ./scripts/health_check.sh
   ```

## 📊 Estrutura dos Jobs

```
Crawler (3:00 AM)
    ↓
Item Collector (3:30 AM)
    ↓
Silver Processor (5:00 AM)
    ↓
Email Notifications (9:00 AM)
```

**Dependências:**
- Item Collector precisa de dados do Crawler
- Silver Processor precisa de dados Bronze (Crawler + Items)
- Email usa dados Silver

## 📁 Estrutura de Arquivos

```
.
├── api/
│   ├── crawler.py              # [MODIFICADO] Sem limites Vercel
│   ├── item_collector.py       # [MODIFICADO] Batch size 500
│   ├── silver_processor.py     # [MODIFICADO] Sem limites
│   ├── notification_service.py # [MODIFICADO] Pool otimizado
│   └── models.py               # [MODIFICADO] Pool otimizado
├── scripts/                     # [NOVO] Scripts wrapper
│   ├── run_crawler.py
│   ├── run_items.py
│   ├── run_silver.py
│   ├── run_emails.py
│   ├── health_check.sh
│   └── README.md
├── deployment/                  # [NOVO] Configs do servidor
│   ├── HETZNER_SETUP.md        # Guia completo
│   ├── pncp-jobs.cron          # Configuração cron
│   ├── pncp-logrotate.conf     # Rotação de logs
│   └── README.md
├── .env                         # [EXISTENTE] Copiar para servidor
└── requirements.txt             # [EXISTENTE] Dependências Python
```

## 🔧 Requisitos do Servidor

**Mínimo Recomendado:**
- **VPS**: Hetzner CX21 (2 vCPU, 4GB RAM, 40GB SSD)
- **OS**: Ubuntu 22.04 LTS
- **Custo**: ~€5-10/mês
- **Python**: 3.11+
- **PostgreSQL**: Acesso remoto configurado

## 📝 Checklist de Deploy

- [ ] Ler [`deployment/HETZNER_SETUP.md`](deployment/HETZNER_SETUP.md)
- [ ] Criar VPS Hetzner
- [ ] Configurar usuário `pncp`
- [ ] Instalar Python 3.11 e dependências
- [ ] Clonar/upload código para `/opt/pncp-jobs`
- [ ] Configurar `.env` no servidor
- [ ] Testar conexão PostgreSQL
- [ ] Instalar cron (`/etc/cron.d/pncp-jobs`)
- [ ] Instalar logrotate (`/etc/logrotate.d/pncp-jobs`)
- [ ] Testar jobs manualmente
- [ ] Aguardar primeira execução automática
- [ ] Monitorar logs nas primeiras 24-48h

## 🎯 Próximos Passos

1. **Seguir guia de setup**: [`deployment/HETZNER_SETUP.md`](deployment/HETZNER_SETUP.md)
2. **Configurar servidor Hetzner** conforme documentação
3. **Testar jobs manualmente** antes de habilitar cron
4. **Monitorar primeira execução** automática
5. **Configurar SMTP produção** (substituir Mailtrap)
6. **Configurar alertas** (opcional)

## 📞 Suporte

Documentação completa disponível em:
- [`deployment/HETZNER_SETUP.md`](deployment/HETZNER_SETUP.md) - Setup completo
- [`scripts/README.md`](scripts/README.md) - Uso dos scripts
- [`deployment/README.md`](deployment/README.md) - Configs do servidor

## 🔍 Monitoramento

**Logs em tempo real:**
```bash
tail -f /var/log/pncp-jobs/*.log
```

**Health check:**
```bash
./scripts/health_check.sh
```

**Status do cron:**
```bash
sudo grep CRON /var/log/syslog | grep pncp
```

**Dados no banco:**
```bash
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM bronze_pncp_licitacoes;"
```

---

**Status:** ✅ Pronto para deploy no Hetzner  
**Última atualização:** 2026-02-09
