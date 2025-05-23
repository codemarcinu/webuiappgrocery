#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_error() {
    echo -e "${RED}[-]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if Python 3.8+ is installed
print_status "Sprawdzanie wersji Pythona..."
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
        print_status "Znaleziono Python $PYTHON_VERSION"
    else
        print_error "Wymagany Python 3.8 lub nowszy. Znaleziono $PYTHON_VERSION"
        exit 1
    fi
else
    print_error "Nie znaleziono Pythona 3"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    print_status "Tworzenie środowiska wirtualnego..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        print_error "Nie udało się utworzyć środowiska wirtualnego"
        exit 1
    fi
fi

# Activate virtual environment
print_status "Aktywowanie środowiska wirtualnego..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    print_error "Nie udało się aktywować środowiska wirtualnego"
    exit 1
fi

# Upgrade pip
print_status "Aktualizacja pip..."
python -m pip install --upgrade pip

# Install dependencies
print_status "Instalacja zależności..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    print_error "Nie udało się zainstalować zależności"
    exit 1
fi

# Check if Ollama is installed and running
print_status "Sprawdzanie statusu Ollama..."
if ! command -v ollama &>/dev/null; then
    print_warning "Ollama nie jest zainstalowana. Instalowanie..."
    curl -fsSL https://ollama.com/install.sh | sh
    if [ $? -ne 0 ]; then
        print_error "Nie udało się zainstalować Ollama"
        exit 1
    fi
fi

# Check if Ollama service is running
if ! systemctl is-active --quiet ollama; then
    print_warning "Usługa Ollama nie jest uruchomiona. Uruchamianie..."
    sudo systemctl start ollama
    if [ $? -ne 0 ]; then
        print_error "Nie udało się uruchomić usługi Ollama"
        exit 1
    fi
fi

# Check if required Ollama model is available
print_status "Sprawdzanie dostępności modelu bielik-local-q8:latest w Ollama..."
if ! ollama list | grep -q "bielik-local-q8:latest"; then
    print_warning "Model bielik-local-q8:latest nie jest zainstalowany w Ollama."
    print_status "Aby pobrać model, wykonaj:"
    echo -e "  ${YELLOW}ollama pull bielik-local-q8${NC}"
    exit 1
else
    print_status "Model bielik-local-q8:latest jest dostępny w Ollama."
fi

# Create necessary directories
print_status "Tworzenie wymaganych katalogów..."
mkdir -p uploads static/thumbnails logs

# Set up database
print_status "Inicjalizacja bazy danych..."
python -c "from database import create_db_and_tables; create_db_and_tables()"
if [ $? -ne 0 ]; then
    print_error "Nie udało się zainicjalizować bazy danych"
    exit 1
fi

print_status "Konfiguracja zakończona pomyślnie!"
print_status "Aby uruchomić aplikację, wykonaj:"
echo -e "  ${YELLOW}source venv/bin/activate${NC}"
echo -e "  ${YELLOW}python main.py${NC}" 