# FarmCare 2.0 (FC28)

FarmCare to kontroler klimatu dla szklarni i tuneli wyposazonych w czujniki srodowiskowe, wietrzniki oraz moduly BoneIO. Projekt sklada sie z backendu FastAPI, prostego frontendu oraz zestawu skryptow i konfiguracji umozliwiajacych uruchomienie calosci na urzadzeniu typu SBC (np. Raspberry Pi, Rock Pi, itp.).

## Najwazniejsze funkcje
- Backend FastAPI serwujacy API, websockety i statyczny frontend
- Integracja z czujnikami poprzez MQTT i magistrale RS485 wraz z usrednianiem odczytow
- Sterowanie grupami wietrznikow z ograniczeniami pogodowymi i harmonogramem
- Baza SQLite z SQLAlchemy zapisujaca logi i ostatnie stany
- Konfiguracje ESPHome dla modulow BoneIO oraz uslugi systemd i Nginx

## Wymagania
- Python >= 3.11 (zalecane 64-bit)
- Systemowe pakiety: `git`, `python3-venv`, `python3-pip`, `sqlite3`, `libffi-dev`, `build-essential`
- Do obslugi RS485: konwerter USB-RS485 kompatybilny z minimalmodbus
- Broker MQTT (Mosquitto lub inny zgodny z MQTT 3.1.1)
- Na urzadzeniu z interfejsem graficznym: `chromium-browser`, `xserver-xorg`, `xinit`, `matchbox-window-manager`, `unclutter`

Pakiety Pythona znajduja sie w `requirements.txt`. Mozna skorzystac z `environment.yml`, jesli preferowany jest Conda.

## Przygotowanie urzadzenia produkcyjnego
Ponizej przyklad dla Raspberry Pi OS Lite 64-bit, ale kroki sa analogiczne dla innych dystrybucji Debiana.

1. Zaktualizuj system i zainstaluj niezbedne pakiety:
   ```bash
   sudo apt update
   sudo apt install -y git python3 python3-venv python3-pip sqlite3 libffi-dev build-essential \
       mosquitto mosquitto-clients network-manager xserver-xorg xinit matchbox-window-manager \
       chromium-browser unclutter
   ```
2. Utworz katalog roboczy i pobierz repozytorium (przyklad /opt/farmcare):
   ```bash
   sudo mkdir -p /opt/farmcare
   sudo chown $USER:$USER /opt/farmcare
   git clone https://example.com/farmcare.git /opt/farmcare
   ```
   (podmien adres repozytorium na docelowy modu)
3. Utworz i aktywuj wirtualne srodowisko:
   ```bash
   cd /opt/farmcare
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. Skonfiguruj zmienne srodowiskowe:
   ```bash
   cp config/.env.example config/.env
   nano config/.env
   ```
   Ustaw m.in. `ADMIN_TOKEN`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`.
5. Dostosuj `config/settings.yaml` do instalacji (czasy przejazdu, mapowanie czujnikow, identyfikatory BoneIO).
6. Zainicjalizuj baze danych i wpisy domyslne:
   ```bash
   python scripts/init_db.py
   ```
7. (Opcjonalnie) uruchom skrypt konfigurujacy siec WAN/LAN:
   ```bash
   sudo scripts/configure_network.sh
   ```
8. Skopiuj uslugi systemd:
   ```bash
   sudo cp deploy/farmcare.service /etc/systemd/system/
   sudo cp deploy/kiosk.service /etc/systemd/system/
   ```
   W razie potrzeby zedytuj klauzule `User=` (domyslnie `pi`) tak, aby odpowiadala uzytkownikowi, pod ktorym ma dzialac proces.
9. Wskaz katalog roboczy dla uslug (domyslnie `/opt/farmcare`). Jesli repozytorium znajduje sie w innym miejscu, zaktualizuj pola `WorkingDirectory` oraz `PYTHONPATH` w `farmcare.service`.
10. Zarejestruj uslugi i uruchom backend oraz kiosk:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now farmcare.service
    sudo systemctl enable --now kiosk.service
    ```
11. Sprawdz statusy:
    ```bash
    systemctl status farmcare.service
    journalctl -u farmcare.service -f
    ```

## Tryb kiosk (Chromium)
Serwis `deploy/kiosk.service` uruchamia Chromium w trybie pelnoekranowym. Przed startem upewnij sie, ze:
- Konto wskazane w usludze (`User=`) ma autologowanie do systemu graficznego lub zainstalowano lekkie srodowisko startowane poleceniem `startx`.
- W pliku `/etc/xdg/openbox/autostart` lub w jednostce systemd dlawkowane jest polecenie `startx /usr/bin/chromium-browser --kiosk ...`. Alternatywnie mozna posluzyc sie przygotowana usluga, ktora korzysta z `xinit` i `matchbox-window-manager`.
- Jesli urzadzenie posiada ekran dotykowy, warto wlaczyc `unclutter` (ukrywanie kursora) i `xinput --set-prop` zgodnie z dokumentacja producenta.

Usluga `kiosk.service` zaklada, ze backend jest dostepny pod `http://localhost:8000/static/index.html`. Dostosuj adres URL, jesli uruchamiasz panel na innym hoscie lub porcie.

## Lokalny broker MQTT (Mosquitto)
1. Po instalacji pakietu `mosquitto` (patrz sekcja wyzej) wlacz usluge:
   ```bash
   sudo systemctl enable --now mosquitto.service
   ```
2. Utworz uzytkownika oraz haslo dla polaczen FarmCare/BoneIO (opcjonalnie):
   ```bash
   sudo mosquitto_passwd -c /etc/mosquitto/passwd farmcare
   ```
3. Dodaj plik konfiguracyjny `/etc/mosquitto/conf.d/farmcare.conf`:
   ```
   allow_anonymous false
   password_file /etc/mosquitto/passwd
   listener 1883 0.0.0.0
   persistence true
   persistence_location /var/lib/mosquitto/
   ```
4. Przeladuj usluge:
   ```bash
   sudo systemctl restart mosquitto.service
   ```
5. Ustaw dane logowania w `config/.env` oraz (jesli potrzeba) w plikach BoneIO (sekcja ponizej).

## Konfiguracja BoneIO (ESPHome)
- Plik `boneio/boneio1.yaml` zawiera kompletna konfiguracje dla pierwszego modulu BoneIO. Na starcie wszystkie przelaczniki sa zerowane, a tematy `farmcare/vents/<id>/available` publikowane z flaga `retain`, co pozwala backendowi rozpoznac gotowosc urzadzenia.
- Dla kazdego dodatkowego modulu skopiuj plik i zaktualizuj `topic_prefix`, numery pinow oraz identyfikatory w `config/settings.yaml`.
- Skopiuj wartosci do `boneio/secrets.yaml` (`ethernet_ip`, `mqtt_broker`, ewentualnie dane logowania) i wgraj konfiguracje przy pomocy `esphome run boneio/boneio1.yaml`.

## Uruchomienie w trybie developerskim
Do szybkiego startu lokalnego (bez systemd i kiosku):
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env  # uzupelnij dane
python scripts/init_db.py
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```
Panel uzytkownika bedzie dostepny pod `http://127.0.0.1:8000/static/index.html`.

## Testy
Uruchom testy jednostkowe poleceniem:
```bash
pytest -q
```

## Struktura katalogow
- `backend/` - logika aplikacji, kontroler oraz warstwa bazy danych
- `frontend/` - statyczny dashboard HTML/JS
- `config/` - konfiguracja systemu, pliki `.env`, `settings.yaml`
- `boneio/` - konfiguracje ESPHome dla modulow BoneIO
- `deploy/` - pliki uslug systemd i przykladowa konfiguracja Nginx
- `scripts/` - skrypty pomocnicze (baza, konfiguracja sieci)
- `tests/` - testy jednostkowe projektu

## Przydatne polecenia diagnostyczne
- `journalctl -u farmcare.service -f` - sledzenie logow backendu
- `mosquitto_sub -h <broker> -v -t 'farmcare/#'` - podglad komunikacji MQTT
- `minimalmodbus --scan` - szybki test komunikacji RS485 (zaleznie od systemu)

