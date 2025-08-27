# FarmCare 2.0 (FC28)

FarmCare to kontroler klimatu dla szklarni/tuneli wyposażonych w wietrzniki i czujniki środowiskowe.  
Projekt składa się z backendu FastAPI, prostego frontendu oraz zestawu skryptów i konfiguracji do uruchomienia całości na urządzeniu typu SBC (np. RPi).

## Funkcje
- Backend FastAPI uruchamiany podczas startu systemu i serwujący frontend statyczny
- Integracja z czujnikami poprzez MQTT i magistrale RS485, z możliwością uśredniania odczytów
- Sterowanie wietrznikami w grupach/partiach, z ograniczeniami pogodowymi i harmonogramem dziennym
- Baza SQLite z SQLAlchemy przechowująca stany wietrzników i logi czujników
- Konfiguracja urządzeń BONEIO (ESPHome) do obsługi przekaźników i wejść krańcowych poprzez MQTT
- Skrypt do konfiguracji dwóch interfejsów sieciowych (WAN/LAN) wraz z zaporą iptables (uruchamiany przez `sudo`)

## Wymagania
- Python 3.11
- Zależności: `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `asyncio-mqtt`, `pyyaml`
- Broker MQTT (np. `mosquitto`)
- Opcjonalnie: środowisko wirtualne (`python -m venv .venv`)

## Instalacja
1. Sklonuj repozytorium i przejdź do katalogu projektu.
2. (Opcjonalnie) utwórz i aktywuj wirtualne środowisko:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Zainstaluj wymagane biblioteki:
   ```bash
   pip install fastapi uvicorn sqlalchemy pydantic asyncio-mqtt pyyaml
   ```
4. Skopiuj plik `config/.env.example` do `config/.env` i uzupełnij wartości zmiennych `ADMIN_TOKEN`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME` oraz `MQTT_PASSWORD`.
5. Zainicjalizuj bazę danych i wpisy domyślne:
   ```bash
   python scripts/init_db.py
   ```

6. Skonfiguruj interfejsy sieciowe (na etapie instalacji systemu):
   ```bash
   sudo scripts/configure_network.sh
   ```

## Konfiguracja
- Skopiuj `config/.env.example` do `config/.env` i uzupełnij m.in. `ADMIN_TOKEN`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME` oraz `MQTT_PASSWORD`.
- Główny plik konfiguracyjny: `config/settings.yaml` – parametry sterowania, mapowanie czujników, definicje wietrzników, grupy oraz opcje bezpieczeństwa
- W sekcji `rs485_buses` każdy czujnik może opcjonalnie określić `scale` i `offset`,
  które przeskalowują surowy odczyt zgodnie ze wzorem `value*scale + offset`
- Przykładowe definicje urządzeń BoneIO do wgrania w ESPHome: katalog `boneio/`
- Dodatkowe pliki usług/systemd i Nginx znajdują się w katalogu `deploy/`

## Uruchomienie
1. Uruchom backend (serwer API + frontend statyczny):
   ```bash
   uvicorn backend.app:app --host 0.0.0.0 --port 8000
   ```
2. Panel użytkownika: `http://HOST:8000/static/index.html`
3. Panel instalatora: `http://HOST:8000/static/installer.html`

## Tryb kiosk

Aby uruchomić interfejs w trybie pełnoekranowym (kiosk) w przeglądarce Chromium:

1. Przejdź do katalogu repozytorium `fc28`:
   ```bash
   cd fc28
   ```
   Możesz sprawdzić obecność plików usług:
   ```bash
   ls deploy
   ```
2. Skopiuj pliki usług do katalogu `/etc/systemd/system/`:
   ```bash
   sudo cp $(pwd)/deploy/farmcare.service /etc/systemd/system/
   sudo cp $(pwd)/deploy/kiosk.service /etc/systemd/system/
   ```
3. Włącz i uruchom usługi:
   ```bash
   sudo systemctl enable --now farmcare.service
   sudo systemctl enable --now kiosk.service
   ```

## Testy
Uruchom testy jednostkowe:
```bash
pytest -q
```

## Struktura katalogów
- `backend/` – logika aplikacji, kontroler, warstwa DB i integracje
- `frontend/` – prosty dashboard w czystym HTML/JS
- `config/` – ustawienia systemu i przykładowy plik `.env.example`
- `scripts/` – skrypty pomocnicze (konfiguracja sieci, inicjalizacja bazy)
- `boneio/` – przykładowe konfiguracje ESPHome dla modułów BoneIO
- `deploy/` – przykładowe jednostki systemd i konfiguracja Nginx
- `tests/` – testy jednostkowe

