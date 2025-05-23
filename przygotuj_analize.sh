#!/bin/bash

# Skrypt do kopiowania kluczowych plików i folderów projektu do analizy

# ----------------- Konfiguracja -----------------
# Katalog źródłowy (zakładamy, że skrypt jest uruchamiany z głównego katalogu projektu)
SOURCE_DIR="."
# Nazwa katalogu docelowego, do którego skopiowane zostaną pliki
DEST_DIR="projekt_do_analizy"

# Lista kluczowych plików i folderów do skopiowania
# (ścieżki względne do SOURCE_DIR)
KEY_ITEMS=(
    "apka.txt"
    "database.py"
    "logging_config.py"
    "main.py"
    "models.py"
    "ollama_client.py"
    "README.md"
    "requirements.txt"
    "routes"      # Katalog
    "setup.sh"
    "static"      # Katalog
    "templates"   # Katalog
)
# -------------------------------------------------

echo "Rozpoczynam przygotowanie plików do analizy..."
echo "Katalog źródłowy: $(realpath "$SOURCE_DIR")"
echo "Katalog docelowy: $(realpath "$DEST_DIR")"
echo ""

# --- Tworzenie katalogu docelowego ---
if [ -d "$DEST_DIR" ]; then
    read -r -p "Katalog '$DEST_DIR' już istnieje. Czy chcesz usunąć jego zawartość i kontynuować? (t/n): " choice
    case "$choice" in
      t|T )
        echo "Usuwam zawartość katalogu '$DEST_DIR'..."
        # Usuń zawartość, ale nie sam katalog, aby uniknąć problemów z uprawnieniami, jeśli jest to np. mount point
        find "$DEST_DIR" -mindepth 1 -delete
        ;;
      n|N )
        echo "Przerwano. Nie dokonano zmian w '$DEST_DIR'."
        exit 1
        ;;
      * )
        echo "Nieprawidłowa opcja. Przerwano."
        exit 1
        ;;
    esac
else
    echo "Tworzę katalog '$DEST_DIR'..."
    mkdir -p "$DEST_DIR"
    if [ $? -ne 0 ]; then
        echo "BŁĄD: Nie udało się utworzyć katalogu '$DEST_DIR'. Sprawdź uprawnienia."
        exit 1
    fi
fi

# --- Kopiowanie plików i folderów ---
echo ""
echo "Kopiuję kluczowe pliki i foldery..."

successful_copies=0
skipped_items=0

for item in "${KEY_ITEMS[@]}"; do
    source_item_path="$SOURCE_DIR/$item"
    # Dla plików i katalogów na najwyższym poziomie, ścieżka docelowa to po prostu DEST_DIR
    # cp -r skopiuje zawartość katalogu 'item' do 'DEST_DIR/item'
    # cp skopiuje plik 'item' do 'DEST_DIR/item'

    if [ ! -e "$source_item_path" ]; then
        echo "OSTRZEŻENIE: Element '$source_item_path' nie istnieje i zostanie pominięty."
        skipped_items=$((skipped_items + 1))
        continue
    fi

    if [ -d "$source_item_path" ]; then
        echo "Kopiuję katalog: $item"
        cp -r "$source_item_path" "$DEST_DIR/"
        if [ $? -eq 0 ]; then
            successful_copies=$((successful_copies + 1))
        else
            echo "BŁĄD: Nie udało się skopiować katalogu '$item'."
        fi
    elif [ -f "$source_item_path" ]; then
        echo "Kopiuję plik: $item"
        cp "$source_item_path" "$DEST_DIR/"
        if [ $? -eq 0 ]; then
            successful_copies=$((successful_copies + 1))
        else
            echo "BŁĄD: Nie udało się skopiować pliku '$item'."
        fi
    else
        echo "OSTRZEŻENIE: Element '$source_item_path' nie jest plikiem ani katalogiem i zostanie pominięty."
        skipped_items=$((skipped_items + 1))
    fi
done

echo ""
echo "--------------- Podsumowanie ---------------"
echo "Kopiowanie zakończone."
echo "Pomyślnie skopiowano: $successful_copies elementów."
if [ $skipped_items -gt 0 ]; then
    echo "Pominięto: $skipped_items elementów (nie znaleziono)."
fi
echo "Kluczowe pliki i foldery powinny znajdować się w katalogu: '$DEST_DIR'"
echo ""
echo "Możesz teraz przeanalizować zawartość katalogu '$DEST_DIR'."
echo "Wskazówka: Foldery takie jak 'static' czy 'templates' zostały skopiowane w całości."
echo "Podczas analizy kodu możesz chcieć zignorować niektóre podfoldery (np. 'static/thumbnails/', jeśli istnieją)."
echo "------------------------------------------"