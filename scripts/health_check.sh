#!/bin/bash
#
# Script de Health Check para PNCP Jobs
# Verifica a saúde dos jobs agendados e alerta sobre problemas
#
# Uso: ./health_check.sh
# Cron: 0 * * * * /opt/pncp-jobs/scripts/health_check.sh >> /var/log/pncp-jobs/health.log 2>&1
#

set -euo pipefail

# Configurações
LOG_DIR="/var/log/pncp-jobs"
DB_CONNECTION_STRING="${DATABASE_URL:-}"
MAX_LOG_AGE_HOURS=24
ALERT_EMAIL="${MAILTO:-}"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para logging
log_info() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}[ERROR]${NC} $1"
}

# Função para enviar alerta (placeholder)
send_alert() {
    local message="$1"
    log_error "$message"
    
    # Se ALERT_EMAIL estiver configurado, enviar email (requer mailutils)
    if [ -n "$ALERT_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "PNCP Jobs - Health Check Alert" "$ALERT_EMAIL"
    fi
}

# Verificar se o diretório de logs existe
check_log_directory() {
    log_info "Verificando diretório de logs..."
    
    if [ ! -d "$LOG_DIR" ]; then
        log_error "Diretório de logs não encontrado: $LOG_DIR"
        return 1
    fi
    
    if [ ! -w "$LOG_DIR" ]; then
        log_error "Sem permissão de escrita em: $LOG_DIR"
        return 1
    fi
    
    log_info "✓ Diretório de logs OK"
    return 0
}

# Verificar idade dos logs (última execução)
check_log_freshness() {
    log_info "Verificando atualização dos logs..."
    
    local issues=0
    local jobs=("crawler" "items" "silver" "emails")
    
    for job in "${jobs[@]}"; do
        local log_file="$LOG_DIR/${job}.log"
        
        if [ ! -f "$log_file" ]; then
            log_warn "Log não encontrado: ${job}.log"
            continue
        fi
        
        # Verificar idade do arquivo
        local file_age_hours=$(( ( $(date +%s) - $(stat -c %Y "$log_file") ) / 3600 ))
        
        if [ $file_age_hours -gt $MAX_LOG_AGE_HOURS ]; then
            log_warn "⚠️  Log de ${job} desatualizado (${file_age_hours}h sem modificação)"
            issues=$((issues + 1))
        else
            log_info "✓ Log de ${job} atualizado (${file_age_hours}h atrás)"
        fi
    done
    
    if [ $issues -gt 0 ]; then
        log_warn "$issues job(s) com logs desatualizados"
        return 1
    fi
    
    return 0
}

# Verificar erros recentes nos logs
check_log_errors() {
    log_info "Verificando erros recentes nos logs..."
    
    local error_count=0
    local jobs=("crawler" "items" "silver" "emails")
    
    for job in "${jobs[@]}"; do
        local log_file="$LOG_DIR/${job}.log"
        
        if [ ! -f "$log_file" ]; then
            continue
        fi
        
        # Contar ERRORs nas últimas 100 linhas
        local errors=$(tail -n 100 "$log_file" | grep -c "ERROR" || true)
        
        if [ $errors -gt 0 ]; then
            log_warn "⚠️  ${job}: ${errors} erro(s) encontrado(s) nas últimas 100 linhas"
            error_count=$((error_count + errors))
            
            # Mostrar últimos 3 erros
            log_warn "Últimos erros:"
            tail -n 100 "$log_file" | grep "ERROR" | tail -n 3 | while read -r line; do
                log_warn "  → $line"
            done
        else
            log_info "✓ ${job}: Sem erros recentes"
        fi
    done
    
    if [ $error_count -gt 5 ]; then
        send_alert "Muitos erros detectados nos logs: $error_count erros"
        return 1
    fi
    
    return 0
}

# Verificar tamanho dos logs
check_log_size() {
    log_info "Verificando tamanho dos logs..."
    
    local total_size=$(du -sm "$LOG_DIR" 2>/dev/null | cut -f1)
    local max_size_mb=500
    
    if [ "$total_size" -gt "$max_size_mb" ]; then
        log_warn "⚠️  Logs muito grandes: ${total_size}MB (limite: ${max_size_mb}MB)"
        log_warn "Considere executar: sudo logrotate -f /etc/logrotate.d/pncp-jobs"
        return 1
    fi
    
    log_info "✓ Tamanho dos logs OK: ${total_size}MB"
    return 0
}

# Verificar processos Python em execução
check_running_processes() {
    log_info "Verificando processos em execução..."
    
    local python_procs=$(pgrep -f "python.*scripts/run_" | wc -l)
    
    if [ "$python_procs" -gt 0 ]; then
        log_info "✓ $python_procs job(s) Python em execução"
        pgrep -af "python.*scripts/run_" | while read -r line; do
            log_info "  → $line"
        done
    else
        log_info "Nenhum job em execução no momento (normal entre execuções)"
    fi
    
    return 0
}

# Verificar cron job configurado
check_cron_config() {
    log_info "Verificando configuração do cron..."
    
    if [ ! -f "/etc/cron.d/pncp-jobs" ]; then
        log_error "❌ Arquivo cron não encontrado: /etc/cron.d/pncp-jobs"
        return 1
    fi
    
    # Verificar permissões (deve ser 644)
    local perms=$(stat -c %a "/etc/cron.d/pncp-jobs")
    if [ "$perms" != "644" ]; then
        log_warn "⚠️  Permissões incorretas no cron: $perms (esperado: 644)"
        return 1
    fi
    
    log_info "✓ Configuração do cron OK"
    return 0
}

# Verificar conectividade com banco de dados
check_database_connection() {
    log_info "Verificando conexão com banco de dados..."
    
    # Carregar .env se existir
    if [ -f "/opt/pncp-jobs/.env" ]; then
        source /opt/pncp-jobs/.env
    fi
    
    if [ -z "$DATABASE_URL" ]; then
        log_warn "⚠️  DATABASE_URL não configurado"
        return 1
    fi
    
    # Tentar conexão simples (requer psql instalado)
    if command -v psql &> /dev/null; then
        if psql "$DATABASE_URL" -c "SELECT 1;" &> /dev/null; then
            log_info "✓ Conexão com banco de dados OK"
            
            # Verificar contadores básicos
            local licitacoes=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM bronze_pncp_licitacoes;" 2>/dev/null | tr -d ' ')
            local itens=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM bronze_pncp_itens;" 2>/dev/null | tr -d ' ')
            
            log_info "  → Licitações bronze: $licitacoes"
            log_info "  → Itens bronze: $itens"
        else
            log_error "❌ Falha ao conectar no banco de dados"
            return 1
        fi
    else
        log_warn "psql não instalado, pulando teste de conexão"
    fi
    
    return 0
}

# Verificar uso de disco
check_disk_space() {
    log_info "Verificando espaço em disco..."
    
    local disk_usage=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
    local max_usage=85
    
    if [ "$disk_usage" -gt "$max_usage" ]; then
        log_error "❌ Disco cheio: ${disk_usage}% usado (limite: ${max_usage}%)"
        send_alert "Espaço em disco crítico: ${disk_usage}% usado"
        return 1
    fi
    
    log_info "✓ Espaço em disco OK: ${disk_usage}% usado"
    return 0
}

# Verificar uso de memória
check_memory() {
    log_info "Verificando uso de memória..."
    
    local mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
    local max_usage=90
    
    if [ "$mem_usage" -gt "$max_usage" ]; then
        log_warn "⚠️  Uso alto de memória: ${mem_usage}%"
        return 1
    fi
    
    log_info "✓ Uso de memória OK: ${mem_usage}%"
    return 0
}

# Função principal
main() {
    echo ""
    log_info "=========================================="
    log_info "PNCP Jobs - Health Check"
    log_info "$(date '+%Y-%m-%d %H:%M:%S')"
    log_info "=========================================="
    echo ""
    
    local overall_status=0
    
    # Executar todos os checks
    check_log_directory || overall_status=1
    echo ""
    
    check_log_freshness || overall_status=1
    echo ""
    
    check_log_errors || overall_status=1
    echo ""
    
    check_log_size || overall_status=1
    echo ""
    
    check_running_processes || overall_status=1
    echo ""
    
    check_cron_config || overall_status=1
    echo ""
    
    check_database_connection || overall_status=1
    echo ""
    
    check_disk_space || overall_status=1
    echo ""
    
    check_memory || overall_status=1
    echo ""
    
    # Resultado final
    log_info "=========================================="
    if [ $overall_status -eq 0 ]; then
        log_info "✅ HEALTH CHECK PASSOU - Tudo OK"
    else
        log_warn "⚠️  HEALTH CHECK COM AVISOS - Revisar acima"
    fi
    log_info "=========================================="
    echo ""
    
    return $overall_status
}

# Executar
main
exit $?
