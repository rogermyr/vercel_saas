#!/bin/bash

# Script para verificar a configuração do Git no servidor Hetzner
# Execute no servidor: bash deployment/verify_git_setup.sh

cd /opt/pncp-jobs

echo "🔍 Verificando configuração do Git..."
echo ""

# Verificar se é um repositório Git
if [ -d .git ]; then
    echo "✅ Diretório .git encontrado"
else
    echo "❌ Diretório .git NÃO encontrado"
    echo ""
    echo "Para inicializar o Git, execute:"
    echo "  cd /opt/pncp-jobs"
    echo "  git init"
    echo "  git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git"
    echo "  git branch -M main"
    echo "  git fetch origin"
    echo "  git reset --hard origin/main"
    exit 1
fi

# Verificar remote origin
echo ""
echo "📡 Remote configurado:"
git remote -v

# Verificar branch atual
echo ""
echo "🌿 Branch atual:"
git branch --show-current

# Verificar status
echo ""
echo "📊 Status do repositório:"
git status

# Verificar último commit
echo ""
echo "📝 Último commit:"
git log -1 --oneline

# Tentar fazer git pull
echo ""
echo "🔄 Testando git pull..."
if git pull origin main --dry-run 2>&1; then
    echo "✅ Git pull funcionando corretamente"
else
    echo "⚠️ Git pull pode ter problemas"
    echo ""
    echo "Possíveis soluções:"
    echo "1. Configure autenticação SSH: ssh-keygen e adicione a chave no GitHub"
    echo "2. Ou use HTTPS com token: git remote set-url origin https://TOKEN@github.com/USER/REPO.git"
fi

echo ""
echo "✅ Verificação concluída!"
