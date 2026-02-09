# Scripts de Jobs PNCP

Scripts wrapper para executar os jobs agendados do sistema PNCP no Hetzner.

## Estrutura

- **run_pipeline.py** - Pipeline completo: Crawler → Items → Silver
- **run_emails.py** - Envia notificações por email
- **run_crawler.py** - Coleta licitações da API do PNCP (uso manual)
- **run_items.py** - Coleta itens das licitações (uso manual)
- **run_silver.py** - Processa dados Bronze → Silver (uso manual)

## Uso Local (Desenvolvimento)

```bash
# Teste do pipeline completo (recomendado)
cd /opt/pncp-jobs
source venv/bin/activate

python scripts/run_pipeline.py  # Executa: Crawler → Items → Silver

# Testar envio de emails
python scripts/run_emails.py

# OU testar jobs individuais para debug
python scripts/run_crawler.py
python scripts/run_items.py
python scripts/run_silver.py
```

## Logs

Todos os jobs gravam logs em `/var/log/pncp-jobs/`:

- `pipeline.log` - Logs do pipeline completo (Crawler → Items → Silver)
- `emails.log` - Logs de envio de emails
- `crawler.log` - Logs do crawler (execução manual)
- `items.log` - Logs da coleta de itens (execução manual)
- `silver.log` - Logs do processamento Silver (execução manual)

Os logs incluem timestamps, níveis e stack traces completos em caso de erro.

## Códigos de Saída

- `0` - Sucesso
- `1` - Erro (detalhes no log)

## Ordem de Execução Recomendada

### Jobs Agendados (Cron):

1. **Pipeline Completo** (8:00 AM)
   - Crawler: Coleta licitações
   - Items: Coleta itens das licitações coletadas
   - Silver: Transforma dados Bronze → Silver
   
2. **Emails** (10:00 AM)
   - Envia notificações baseadas em dados Silver

**Vantagens do Pipeline Único:**
- Garante ordem de execução
- Se uma etapa falha, as seguintes não executam (economia de recursos)
- Logs unificados facilitam debug
- Simplifica gerenciamento

### Execução Manual (Debug):

Para debug ou reprocessamento, você pode executar os jobs individuais:

```bash
python scripts/run_crawler.py   # Apenas Crawler
python scripts/run_items.py     # Apenas Items
python scripts/run_silver.py    # Apenas Silver
```

## Configuração de Cron

Veja `/etc/cron.d/pncp-jobs` para a configuração dos agendamentos:

- **08:00** - Pipeline completo (run_pipeline.py)
- **10:00** - Notificações por email (run_emails.py)
