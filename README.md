# FarmCare 2.0 (FC28)

FarmCare to kontroler klimatu dla szklarni i tuneli wyposazonych w czujniki srodowiskowe, wietrzniki oraz moduly BoneIO. Projekt sklada sie z backendu FastAPI, prostego frontendu oraz zestawu skryptow i konfiguracji umozliwiajacych uruchomienie calosci na urzadzeniu typu SBC (np. Raspberry Pi, Rock Pi, itp.). Ponizszy przewodnik przeprowadza przez kompletna instalacje oraz wstepna konfiguracje urzadzenia.

> **Uwaga (aktualizacja):** Zaktualizowano instrukcje pod katem typowych bledow napotykanych przy instalacji (Mosquitto/persistence, siec/iptables, backend/uvicorn, healthcheck, kiosk, BoneIO).

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
   > Uwaga: `requirements.txt` zawiera pin `pydantic<2`, aby zachowac zgodnosc z aktualnym modulem konfiguracji. Jesli w systemie masz juz Pydantic 2.x, odinstaluj go przed instalacja zaleznosci z pliku.
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
- `rs485_buses` - konfiguracja magistral RS485. Dla kazdego portu ustaw `name`, `port`, parametry transmisji oraz liste `sensors`. Przy czujnikach SenseCAP uzyj driverow `sensecap_sco2_03b` (CO2/temperatura/wilgotnosc) i `sensecap_s500_v2` (stacja pogodowa):
  ```yaml
  rs485_buses:
    - name: "internal_bus"
      port: "/dev/ttyUSB0"
      sensors:
        - driver: "sensecap_sco2_03b"
          slave: 45  # domyslny adres SenseCAP S-CO2-03B
          outputs:
            co2: "internal_co2"
            temperature: "internal_temp"
            humidity: "internal_hum"
    - name: "external_bus"
      port: "/dev/ttyUSB1"
      sensors:
        - driver: "sensecap_s500_v2"
          slave: 10  # domyslny adres SenseCAP S500 V2
          outputs:
            air_temperature: "external_temp"
            air_humidity: "external_hum"
            barometric_pressure: "external_pressure"
            wind_direction_avg: "wind_direction"
            wind_speed_avg: "wind_speed"
            wind_speed_max: "wind_gust"
  ```
  Driver `sensecap_sco2_03b` przelicza temperature i wilgotnosc dzielac wartosci rejestrowe przez 100, a `sensecap_s500_v2` dzieli odczyty przez 1000 (temperatura w degC, predkosci w m/s, cisnienie w Pa).

Po zmianach zachowaj plik i przygotuj kopie zapasowa dla zespolu serwisowego.

> Panel instalatora i dashboard zapisuje nadpisane progi w bazie (tabela `settings`). Przy starcie backend naklada je na wartosci z pliku, dlatego zmiany wykonane w trakcie pracy nie wymagaja modyfikacji `config/settings.yaml`.

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

### 8. Konfiguracja brokera MQTT (Mosquitto) - **wazne: bez duplikatow**

Mosquitto laduje najpierw `/etc/mosquitto/mosquitto.conf`, a potem pliki z `/etc/mosquitto/conf.d/*.conf`.  
Jesli `persistence` lub `persistence_location` pojawia sie **w obu miejscach**, broker nie wystartuje.

**Zalecenie:** w `/etc/mosquitto/conf.d/farmcare.conf` dodaj tylko to, co dotyczy bezpieczenstwa i listenera:
```ini
# /etc/mosquitto/conf.d/farmcare.conf
allow_anonymous false
password_file /etc/mosquitto/passwd
listener 1883 0.0.0.0
```
> Jesli chcesz ustawic `persistence`/`persistence_location`, zrob to **w jednym** miejscu (albo w glownym `mosquitto.conf`, albo w `farmcare.conf` - ale nie w obu).

Utworz uzytkownika i haslo:
```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd farmcare
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd
sudo chmod 640 /etc/mosquitto/passwd
```

**Test (foreground)** - bez wymuszania portu:
```bash
sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v
# (Ctrl+C aby wyjsc, jesli nie ma bledow)
sudo systemctl restart mosquitto
sudo systemctl status mosquitto --no-pager
```

### 9. Konfiguracja sieci (WAN+LAN) - "Address already assigned", `ip_forward`, `iptables`

Jesli skrypt ustawial juz adres i uruchamiasz go ponownie, mozesz zobaczyc:
`Error: ipv4: Address already assigned.`  
Uzyj idempotentnego dodawania IP:
```bash
ip addr replace "${LAN_ADDR}" dev "${LAN_IF}"
```

Wlacz IP forwarding **teraz i na stale**:
```bash
sudo sysctl -w net.ipv4.ip_forward=1
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-farmcare.conf
sudo sysctl --system
```

Jesli pojawi sie `iptables: command not found`, doinstaluj:
```bash
sudo apt-get update && sudo apt-get install -y iptables
```

> W skrypcie mozesz dodac u gory:
> ```bash
> set -euo pipefail
> command -v iptables >/dev/null || { echo "Brak iptables (sudo apt-get install -y iptables)"; exit 1; }
> ```

### 10. Backend (FastAPI) - wlasciwy modul, venv i unit systemd

Kod backendu znajduje sie w katalogu `backend/`. Uruchamiamy Uvicorn z modulem **`backend.app:app`**.

> Zalecany venv: `/opt/farmcare/venv`  
> Zaleznosci: `pip install -r /opt/farmcare/requirements.txt`

Przykladowa jednostka:
```ini
[Unit]
Description=FarmCare Backend (FastAPI)
After=network-online.target mosquitto.service
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
User=farmcare
Group=farmcare
WorkingDirectory=/opt/farmcare
Environment="PYTHONPATH=/opt/farmcare"
Environment="PORT=8000"
ExecStart=/opt/farmcare/venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=multi-user.target
```

### 11. Healthcheck

W aktualnej wersji aplikacji nie ma `/api/health`.  
Uzyj:
```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/api/state
```
*(Opcjonalnie mozesz dodac lekki endpoint `GET /api/health`, jesli wymaga tego monitoring.)*

### 12. Kiosk (Chromium) - autostart przez systemd + `~/.xinitrc`

Nie uruchamiaj `startx` z `~/.bash_profile`.  
Zamiast tego:

1) `~/.xinitrc` uzytkownika kiosku:
```sh
xset s off; xset -dpms; xset s noblank
matchbox-window-manager &    # lub openbox-session
exec chromium-browser --noerrdialogs --disable-session-crashed-bubble --disable-infobars \
  --kiosk http://localhost:8000/static/index.html --incognito
```
2) Usluga `/etc/systemd/system/kiosk.service`:
```ini
[Unit]
Description=Chromium Kiosk via Xorg
After=systemd-user-sessions.service network-online.target
Wants=network-online.target

[Service]
User=farmcare
Group=farmcare
WorkingDirectory=/home/farmcare
Environment=DISPLAY=:0
ExecStart=/usr/bin/startx /home/farmcare/.xinitrc -- -nocursor
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=multi-user.target
```
Nastepnie:
```bash
sudo systemctl daemon-reload
sudo systemctl enable kiosk
sudo systemctl start kiosk
```

### 13. BoneIO / ESPHome - Ethernet i broker 192.168.50.1

Konfiguracja uzywa Ethernetu i wskazuje brokera z `secrets.yaml`:
```yaml
# boneio1.yaml (fragment)
ethernet:
  type: LAN8720
  manual_ip:
    static_ip: !secret ethernet_ip
    gateway:   !secret ethernet_gateway
    subnet:    !secret ethernet_subnet
    dns1:      !secret ethernet_dns

mqtt:
  broker: !secret mqtt_broker
```
Przykladowe wartosci w `boneio/secrets.yaml`:
```yaml
ethernet_ip: 192.168.50.2
ethernet_gateway: 192.168.50.1
ethernet_subnet: 255.255.255.0
ethernet_dns: 192.168.50.1
mqtt_broker: 192.168.50.1
```

### 14. Podglad MQTT (debug)

```bash
mosquitto_sub -h 127.0.0.1 -t '#' -v
mosquitto_sub -h 127.0.0.1 -t '$SYS/#' -v
mosquitto_pub  -h 127.0.0.1 -t test/farmcare -m hi
```

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
Przed uruchomieniem zainstaluj zaleznosc testowa (`pip install pytest`) i uruchom testy jednostkowe:
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



