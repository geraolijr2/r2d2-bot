#!/bin/bash
set -e

echo "Iniciando setup do projeto R2D2-BOT (idempotente)..."

# ==============================
# Configuráveis
# ==============================
REPO_URL="${REPO_URL:-https://github.com/geraolijr2/r2d2-bot.git}"
PROJECT_DIR="$HOME/R2D2-BOT"
PYTHON_FORMULA="python@3.11"
AUTO_RUN_STREAMLIT="${AUTO_RUN_STREAMLIT:-1}"

# ==============================
# Homebrew, Git e Python
# ==============================
if ! command -v brew >/dev/null 2>&1; then
  echo "Instalando Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
  echo "Homebrew já instalado."
fi

echo "Garantindo Git e Python 3.11..."
brew install git $PYTHON_FORMULA || true
brew link $PYTHON_FORMULA --force || true

# ==============================
# Projeto
# ==============================
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

if [ ! -d ".git" ]; then
  echo "Clonando repositório em $PROJECT_DIR..."
  git clone "$REPO_URL" .
else
  echo "Repositório já existe. Atualizando..."
  git pull
fi

# ==============================
# Virtualenv
# ==============================
if [ ! -d "venv" ]; then
  echo "Criando ambiente virtual..."
  python3 -m venv venv
else
  echo "Ambiente virtual já existe."
fi

echo "Ativando ambiente virtual..."
# shellcheck source=/dev/null
source venv/bin/activate

echo "Atualizando pip..."
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
  echo "Instalando dependências do requirements.txt..."
  pip install -r requirements.txt
else
  echo "requirements.txt não encontrado. Pulando."
fi

# ==============================
# Streamlit secrets
# ==============================
SECRETS_DIR="$HOME/.streamlit"
SECRETS_FILE="$SECRETS_DIR/secrets.toml"
mkdir -p "$SECRETS_DIR"

if [ ! -f "$SECRETS_FILE" ]; then
  echo "Criando $SECRETS_FILE padrão..."
  cat > "$SECRETS_FILE" <<'EOT'
SUPABASE_URL="https://ksvfbmgdattckzdxgpjy.supabase.co"
SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzdmZibWdkYXR0Y2t6ZHhncGp5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1ODkzMzM2MywiZXhwIjoyMDc0NTA5MzYzfQ.serchg2XlXqDYegRth6FOn28wMPoAw6C_Q7LBt0AbIY"
SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzdmZibWdkYXR0Y2t6ZHhncGp5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTg5MzMzNjMsImV4cCI6MjA3NDUwOTM2M30.X0Lp8qBCYZJK1D95qSoIj5zDoxX1hsvp7_AsyegAVEo"
BYBIT_API_KEY="LEyYjMYRcSa3Xc7T5W"
BYBIT_API_SECRET="iImyzKWmNFFXlnmyeUBddr9j66nJ8jbD3xqm"
EOT
else
  echo "Secrets já existem em $SECRETS_FILE (não sobrescrito)."
fi

# ==============================
# .env com as chaves fornecidas
# ==============================
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Criando $ENV_FILE..."
  cat > "$ENV_FILE" <<'EOT'
SUPABASE_URL="https://ksvfbmgdattckzdxgpjy.supabase.co"
SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzdmZibWdkYXR0Y2t6ZHhncGp5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1ODkzMzM2MywiZXhwIjoyMDc0NTA5MzYzfQ.serchg2XlXqDYegRth6FOn28wMPoAw6C_Q7LBt0AbIY"
SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzdmZibWdkYXR0Y2t6ZHhncGp5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTg5MzMzNjMsImV4cCI6MjA3NDUwOTM2M30.X0Lp8qBCYZJK1D95qSoIj5zDoxX1hsvp7_AsyegAVEo"
BYBIT_API_KEY="LEyYjMYRcSa3Xc7T5W"
BYBIT_API_SECRET="iImyzKWmNFFXlnmyeUBddr9j66nJ8jbD3xqm"
EOT
else
  echo "$ENV_FILE já existe (não sobrescrito)."
fi

# ==============================
# Garantir .gitignore para não versionar .env
# ==============================
if [ ! -f ".gitignore" ]; then
  touch .gitignore
fi
if ! grep -qE '^\.env$' .gitignore; then
  echo ".env" >> .gitignore
  echo "Adicionado .env ao .gitignore."
fi

# ==============================
# Auto-source do .env ao ativar o venv
# ==============================
ACTIVATE_FILE="venv/bin/activate"
if ! grep -q "BEGIN auto-source .env" "$ACTIVATE_FILE"; then
  echo "Configurando auto-source do .env no activate do venv..."
  cat >> "$ACTIVATE_FILE" <<'EOF'

# BEGIN auto-source .env
if [ -f "$VIRTUAL_ENV/../.env" ]; then
  set -a
  . "$VIRTUAL_ENV/../.env"
  set +a
fi
# END auto-source .env
EOF
fi

# ==============================
# Mensagem final e execução
# ==============================
echo
echo "Setup concluído."
echo "Projeto: $PROJECT_DIR"
echo "Ativar venv:  source $PROJECT_DIR/venv/bin/activate"
echo


