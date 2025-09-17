# FarmCare 2.0 (FC28)

FarmCare to kontroler klimatu dla szklarni i tuneli wyposazonych w czujniki srodowiskowe, wietrzniki oraz moduly BoneIO. Projekt sklada sie z backendu FastAPI, prostego frontendu oraz zestawu skryptow i konfiguracji umozliwiajacych uruchomienie calosci na urzadzeniu typu SBC (np. Raspberry Pi, Rock Pi, itp.). Ponizszy przewodnik przeprowadza przez kompletna instalacje oraz wstepna konfiguracje urzadzenia.

## Najwazniejsze funkcje
- Backend FastAPI serwujacy API, websockety i statyczny frontend
- Integracja z czujnikami poprzez MQTT i magistrale RS485 wraz z usrednianiem odczytow
- Sterowanie grupami wietrznikow z ograniczeniami pogodowymi i harmonogramem
- Baza SQLite z SQLAlchemy zapisujaca logi i ostatnie stany
- Konfiguracje ESPHome dla modulow BoneIO oraz uslugi systemd i Nginx

## Sprzet i wymagania systemowe
### Sprzet
- Komputer jednoplytowy (Raspberry Pi 4 4GB lub odpowiednik z Linuxem 64-bit)
- Karta microSD (min. 16 GB) lub inny nosnik dla systemu
- Moduly BoneIO oparte na ESP32 z odpowiednia konfiguracja przekaznikow
- Czujniki srodowiskowe na magistrali RS485 (np. temperatura, wilgotnosc, wiatr, deszcz)
- Konwerter USB-RS485 kompatybilny z minimalmodbus
- Siec Ethernet lub Wi-Fi oraz (opcjonalnie) ekran dotykowy z interfejsem USB/HDMI
- Zasilacze dla SBC i modulow wykonawczych zgodnie ze specyfikacja urzadzen

### Oprogramowanie
- Python >= 3.11 (zalecane 64-bit)
- Systemowe pakiety: `git`, `python3-venv`, `python3-pip`, `sqlite3`, `libffi-dev`, `build-essential`
- Broker MQTT (Mosquitto lub inny zgodny z MQTT 3.1.1)
- Dla RS485: sterowniki konwertera USB oraz pakiet `minimalmodbus` (instalowany z `requirements.txt`)
- Na urzadzeniu z interfejsem graficznym: `chromium-browser` (lub `chromium`), `xserver-xorg`, `xinit`, `matchbox-window-manager`, `unclutter`
- (Opcjonalnie) `esphome` do wgrywania konfiguracji na BoneIO

### Konta systemowe i katalogi
- Przyklady zakladaja uzytkownika `pi` oraz katalog roboczy `/opt/farmcare`. Jesli korzystasz z innego uzytkownika lub sciezki, dostosuj polecenia, pliki `.service` i zmienne w README.
- Upewnij sie, ze uzytkownik ma dostep do portow szeregowych (`dialout`) oraz do katalogow `/opt/farmcare`, `/var/www/farmcare_frontend` (jesli uzywasz Nginx) i plikow uslug systemd.

## Instalacja produkcyjna (krok po kroku)
### 1. Przygotowanie systemu operacyjnego
1. Zaktualizuj system i zainstaluj wymagane pakiety:
   ```bash
   sudo apt update
   sudo apt install -y git python3 python3-venv python3-pip sqlite3 libffi-dev build-essential \
       mosquitto mosquitto-clients network-manager xserver-xorg xinit matchbox-window-manager \
       chromium-browser unclutter
   ```
2. Skonfiguruj hostname, strefe czasowa, klawiature oraz SSH zgodnie z polityka instalacji (`sudo raspi-config` na Raspberry Pi).
3. Zweryfikuj, ze konwertery RS485 sa widoczne jako `/dev/ttyUSB*` (`dmesg | tail`, `ls /dev/ttyUSB*`).

### 2. Pobranie repozytorium
1. Utworz katalog roboczy i nadaj prawa uzytkownikowi, pod ktorym ma dzialac aplikacja:
   ```bash
   sudo mkdir -p /opt/farmcare
   sudo chown $USER:$USER /opt/farmcare
   ```
2. Sklonuj repozytorium:
   ```bash
   git clone https://example.com/farmcare.git /opt/farmcare
   ```
   Zastep adres repozytorium wlasnym zrodlem (HTTP(S), SSH lub lokalne archiwum).

### 3. Srodowisko uruchomieniowe i zaleznosci
1. Przejdz do katalogu projektu i utworz wirtualne srodowisko:
   ```bash
   cd /opt/farmcare
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Zaktualizuj `pip` oraz zainstaluj zaleznosci:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
   Alternatywnie mozesz skorzystac z `environment.yml`, jesli preferujesz Conda.

### 4. Konfiguracja zmiennych srodowiskowych (`config/.env`)
1. Skopiuj przykladowy plik:
   ```bash
   cp config/.env.example config/.env
   ```
2. Uzupelnij wartosci (przyklad edycji w `nano`):
   ```bash
   nano config/.env
   ```
   Kluczowe pola:
   - `ADMIN_TOKEN` - token wymagany do uwierzytelniania panelu administracyjnego (ustaw wlasny, losowy ciag).
   - `MQTT_HOST` / `MQTT_PORT` - adres brokera MQTT, z ktorym laczy sie backend.
   - `MQTT_USERNAME` / `MQTT_PASSWORD` - dane logowania do brokera (pozostaw puste dla polaczen anonimowych).
   - (Opcjonalnie) inne zmienne zdefiniowane w `backend/core/config.py`, np. `API_HOST`, `API_PORT`, jesli potrzebujesz nadpisac.

### 5. Konfiguracja pliku `config/settings.yaml`
Plik `config/settings.yaml` definiuje logike sterowania. Dostosuj go do instalacji:
- Sekcja `control` - progi temperatury, wilgotnosci, predkosci wiatru oraz opoznienia ruchu. Ustaw `target_temp_c`, `humidity_thr`, `wind_risk_ms`, `wind_crit_ms` zgodnie z wymaganiami uprawy.
- `rs485_buses` - lista magistral RS485. Dla kazdej z nich ustaw port (`/dev/ttyUSBx`) oraz mapowania rejestrow na logiczne nazwy (`map_to`). Parametry `scale` i `offset` pozwalaja skalowac wartosc z czujnika.
- `sensors` - powiazania tematow MQTT z nazwami czujnikow uzywanymi w systemie. Ustaw `topic` i (opcjonalnie) `avg_window_s`.
- `boneio_devices` - identyfikatory modulow BoneIO oraz ich `base_topic`. Musza odpowiadac temu, co wysyla ESPHome.
- `vent_defaults` i `vents` - konfiguracja wietrznikow. Zmierz realny czas przejazdu (`travel_time_s`), uzupelnij tematy MQTT `up`, `down`, `error_in` oraz przypisz `boneio_device`.
- `vent_groups` i `vent_plan` - grupy i harmonogram otwierania/zamykania. Zdefiniuj grupy logiczne, kolejnosc dzialania (`parallel`/`serial`), `step_percent` i opoznienia pomiedzy etapami.
- `security.require_token` - ustaw na `false`, jesli lokalna siec nie wymaga tokena w naglowku `x-admin-token`.

Po zmianach zachowaj plik i przygotuj kopie zapasowa dla zespolu serwisowego.

### 6. Konfiguracja BoneIO (ESPHome)
1. W pliku `boneio/secrets.yaml` wpisz parametry sieci oraz adres brokera:
   ```yaml
   ethernet_ip: 192.168.50.2
   ethernet_gateway: 192.168.50.1
   ethernet_subnet: 255.255.255.0
   ethernet_dns: 192.168.50.1
   mqtt_broker: 192.168.50.1
   ```
   Dostosuj te wartosci do topologii sieci.
2. Dostosuj `boneio/boneio1.yaml`:
   - Zmien `topic_prefix`, numery pinow GPIO i liste wietrznikow, jesli uklad jest inny.
   - Zadbaj, aby tematy MQTT pokrywaly sie z wpisami w `config/settings.yaml`.
   - Uzupelnij dodatkowe moduly BoneIO kopiujac plik i aktualizujac identyfikatory.
3. Wgraj konfiguracje na ESP32 (w wymaganym srodowisku):
   ```bash
   esphome run boneio/boneio1.yaml
   ```
   Po starcie modul publikuje status `farmcare/vents/<id>/available`, co pozwala backendowi wykryc gotowosc.

### 7. Inicjalizacja bazy danych
1. Upewnij sie, ze wirtualne srodowisko jest aktywne.
2. Uruchom skrypt inicjalizujacy:
   ```bash
   python scripts/init_db.py
   ```
   Skrypt utworzy katalog `data/`, baze SQLite `farmcare.sqlite3` oraz domyslne wpisy (tryb `auto`). Mozesz powtorzyc go, jesli baza zostanie usunieta.

### 8. Konfiguracja brokera MQTT
Mozesz uzyc lokalnej instancji Mosquitto lub zewnetrznego brokera.
1. Aktywuj lokalna usluge:
   ```bash
   sudo systemctl enable --now mosquitto.service
   ```
2. (Opcjonalnie) utworz uzytkownika i haslo:
   ```bash
   sudo mosquitto_passwd -c /etc/mosquitto/passwd farmcare
   ```
3. Dodaj plik `/etc/mosquitto/conf.d/farmcare.conf`:
   ```
   allow_anonymous false
   password_file /etc/mosquitto/passwd
   listener 1883 0.0.0.0
   persistence true
   persistence_location /var/lib/mosquitto/
   ```
4. Przeladuj mosquitto:
   ```bash
   sudo systemctl restart mosquitto.service
   ```
5. Wprowadz dane logowania w `config/.env` oraz (w razie potrzeby) w `boneio/secrets.yaml`.

### 9. (Opcjonalnie) Konfiguracja sieci WAN/LAN
Skrypt `scripts/configure_network.sh` przygotowuje izolowana siec LAN dla modulow wykonawczych:
```bash
sudo scripts/configure_network.sh
```
Domyslnie WAN=`eth0`, LAN=`eth1`, a adres LAN to `192.168.50.1/24`. Dostosuj zmienne w skrypcie do swojej infrastruktury lub wykonaj konfiguracje recznie. Skrypt wymaga uruchomienia jako `root`.

### 10. Uslugi systemowe i kiosk
1. Skopiuj pliki uslug systemd na docelowy system:
   ```bash
   sudo cp deploy/farmcare.service /etc/systemd/system/
   sudo cp deploy/kiosk.service /etc/systemd/system/
   ```
2. W plikach `.service` zaktualizuj:
   - `User=` - uzytkownik, pod ktorym dziala backend/kiosk.
   - `WorkingDirectory` i `Environment="PYTHONPATH=..."` (w `farmcare.service`) - wskaz na katalog projektu.
   - `ExecStart` w `kiosk.service` - dopasuj binarne (`/usr/bin/chromium-browser` vs `/usr/bin/chromium`) oraz adres URL panelu.
3. (Opcjonalnie) Aktywuj tunel odwrotny do zdalnego serwera VPS wykorzystujac `deploy/farmcare-tunnel.service` (uzupelnij hosta, uzytkownika i klucz SSH).
4. Przeladuj demon systemd i wlacz uslugi:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now farmcare.service
   sudo systemctl enable --now kiosk.service   # tylko jesli uzywasz kiosku
   ```

### 11. Pierwsze uruchomienie i testy
1. Sprawdz status backendu i kiosku:
   ```bash
   systemctl status farmcare.service
   journalctl -u farmcare.service -f
   ```
2. Zweryfikuj, ze API odpowiada:
   ```bash
   curl http://localhost:8000/api/health
   ```
3. Otworz panel (`http://localhost:8000/static/index.html`) na urzadzeniu lub zdalnie przez tunel/Nginx. Wprowadz `ADMIN_TOKEN`, aby uzyskac dostep administracyjny.
4. Sprawdz, czy czujniki przesylaja dane (`mosquitto_sub -h <broker> -v -t 'farmcare/#'`) oraz czy wietrzniki reaguja na polecenia z panelu (wykonaj krotki ruch i potwierdz, ze czasy przejazdu sa poprawne).
5. Po pierwszym uruchomieniu wykonaj kalibracje wietrznikow z poziomu panelu (plan kalibracji bazuje na `vent_defaults` i `travel_time_s`).

## Aktualizacja oprogramowania
- Zatrzymaj uslugi:
  ```bash
  sudo systemctl stop farmcare.service kiosk.service
  ```
- Pobierz najnowsze zmiany:
  ```bash
  cd /opt/farmcare
  git pull
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- Zastosuj ew. migracje konfiguracji (porownaj `config/.env.example`, `config/settings.yaml` z repozytorium).
- Uruchom ponownie uslugi:
  ```bash
  sudo systemctl start farmcare.service
  sudo systemctl start kiosk.service
  ```

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
Panel uzytkownika bedzie dostepny pod `http://127.0.0.1:8000/static/index.html`. Polecenia mozna wykonac na dowolnym systemie z Pythonem 3.11.

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
- `data/`, `logs/` - katalogi tworzone automatycznie na dane persistentne

## Przydatne polecenia diagnostyczne
- `journalctl -u farmcare.service -f` - sledzenie logow backendu
- `systemctl status farmcare.service` - szybkie sprawdzenie statusu uslugi
- `mosquitto_sub -h <broker> -v -t 'farmcare/#'` - podglad komunikacji MQTT
- `minimalmodbus --scan` - test komunikacji RS485 (zaleznie od systemu)
- `sqlite3 data/farmcare.sqlite3 '.tables'` - wglad do tabel bazy danych
- `esphome logs boneio/boneio1.yaml` - monitorowanie logow z modulu BoneIO w trybie serwisowym
