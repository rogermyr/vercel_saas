# Configuração dos GitHub Secrets

Para habilitar o deploy automático para Hetzner, você precisa configurar 3 secrets no seu repositório GitHub.

## Passo a Passo

1. **Acesse as Configurações do Repositório**
   - Vá para o seu repositório no GitHub
   - Clique em **Settings** (Configurações)
   - No menu lateral, clique em **Secrets and variables** → **Actions**
   - Clique em **New repository secret**

2. **Configure os 3 Secrets**

### Secret 1: HETZNER_HOST
- **Name:** `HETZNER_HOST`
- **Value:** O IP do seu servidor Hetzner
  ```
  135.181.44.221
  ```
  (ou o IP correto do seu servidor)

### Secret 2: HETZNER_USERNAME
- **Name:** `HETZNER_USERNAME`
- **Value:** O usuário SSH do servidor
  ```
  pncp
  ```

### Secret 3: HETZNER_SSH_KEY
- **Name:** `HETZNER_SSH_KEY`
- **Value:** A chave privada SSH completa

**Como obter a chave SSH:**

Na sua máquina local (onde você se conecta ao servidor):

```bash
# Se você usa WSL/Linux
cat ~/.ssh/id_rsa

# Se você usa Windows e tem a chave em outro lugar,
# localize o arquivo da chave privada e copie todo o conteúdo
```

**Importante:** Copie a chave privada COMPLETA, incluindo as linhas:
```
-----BEGIN OPENSSH PRIVATE KEY-----
...conteúdo da chave...
-----END OPENSSH PRIVATE KEY-----
```

Ou se for formato RSA:
```
-----BEGIN RSA PRIVATE KEY-----
...conteúdo da chave...
-----END RSA PRIVATE KEY-----
```

## Como Funciona

Depois de configurar os secrets:

1. **Deploy Automático:** Sempre que você der `git push` para a branch `main`, o GitHub Actions irá:
   - Conectar no servidor via SSH
   - Fazer `git pull` do código
   - Manter o arquivo `.env` intacto
   - Atualizar as dependências Python
   - Fazer health check do banco de dados

2. **Deploy Manual:** Você também pode executar o deploy manualmente:
   - Vá em **Actions** no GitHub
   - Selecione **Deploy PNCP Jobs para Hetzner**
   - Clique em **Run workflow**

## Verificação

Após configurar os secrets, faça um teste:

```bash
# Na sua máquina local
git add .
git commit -m "test: Testando deploy automático"
git push origin main
```

Depois, acompanhe em:
- GitHub → **Actions** → Veja o workflow executando
- Verifique os logs do deploy

## Troubleshooting

**Erro de conexão SSH:**
- Verifique se o IP está correto em `HETZNER_HOST`
- Verifique se o usuário está correto em `HETZNER_USERNAME`
- Confirme que a chave SSH está completa (com BEGIN/END)

**Erro de permissão:**
- Certifique-se de que o usuário `pncp` tem permissão para executar git pull em `/opt/pncp-jobs`
- Verifique se o diretório pertence ao usuário correto

**Git pull falha:**
- Verifique se o git está inicializado no servidor
- Confirme que o remote origin está configurado
