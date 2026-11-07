# Farming Simulator 25 für Pterodactyl

Eigenes Linux/amd64-Image und Pterodactyl-Egg nach der FS25-Vorlage von [CubeCoders AMP](https://github.com/CubeCoders/AMPTemplates). Die Installation verwendet den offiziellen GIANTS-Download und GE-Proton, nicht SteamCMD. Du brauchst einen eigenen GIANTS-Produktschlüssel für den Server und etwa **70 GiB freien Speicher** für die Erstinstallation. Das Disklimit im Panel muss dafür ausreichen.

## Installation

1. Das [fertige Egg herunterladen](https://raw.githubusercontent.com/DasEric/fs25-docker/main/egg-farming-simulator-25.json). Die Image-Adressen sind eingetragen. Das GHCR-Paket muss für Wings lesbar sein (öffentlich oder mit Registry-Zugang).
2. Die JSON-Datei im Pterodactyl-Adminbereich als Egg importieren und einen Server anlegen. Docker-Image und Script Container verwenden dasselbe Image. Standard-Allocations: **10823/UDP** als Hauptport, **8080/TCP** fürs Webinterface, bei TLS zusätzlich **8443/TCP**. Abweichende Webports in den Egg-Variablen an die Allocations anpassen.
3. Unter **Admin → Servers → Startup** am Server **GIANTS Product Key** eintragen. **GIANTS IMG Download Link** ist optional: Mit einem direkten GIANTS-`.img`-Link installierst du gezielt diesen Build; ohne Link sucht der Installer das Hauptspiel im GIANTS-Portal.
4. Im Panel **Start** drücken. Fehlt die Installation, lädt und installiert der Server FS25 und startet es anschließend. Bei späteren Starts erkennt er die vorhandene Installation und überspringt das Setup. Die GIANTS-Oberfläche ist standardmäßig unter `http://NODE-IP:8080` erreichbar. Für TLS `game/cert.pem` und `game/pk.pem` bereitstellen und TLS im Egg einschalten.

Schlüssel nur pro Server eintragen, nie als Standardwert im öffentlichen Egg. Wings kann Variablen ins Installationslog schreiben. Wer das vermeiden will, legt stattdessen `.fs25-secrets/activation-key`, `download-url`, `dlc-product-keys` und `dlc-install-sources` im Servervolume ab (Dateimodus `0600`, Eigentümer wie das Volume) und lässt die Panel-Felder leer. Die optionalen Passwortdateien heißen `web-admin-password`, `game-password` und `ingame-admin-password`.

## DLCs

- **DLC Product Keys:** `pumps=DEIN_KEY;mercedes=DEIN_KEY`
- **DLC Installation Sources:** `pumps=https://cdn20.giants-software.com/…/installer.exe;mercedes=mercedes.img`

Die Namen müssen übereinstimmen. Als Quelle gehen direkte GIANTS-`.exe`-/`.img`-Links oder hochgeladene Dateien relativ zu `dlc-installers/`. Ohne Quelle sucht das Egg die DLCs zum jeweiligen Key im GIANTS-Portal. Nach Änderungen neu starten; um Downloads mit unveränderten Links oder Dateinamen zu aktualisieren, **Reinstall** ausführen. Das Egg installiert DLCs im selben Proton-Prefix, aktiviert sie über die offiziellen Installer und überspringt bereits verifizierte DLCs. Das Entfernen eines Listeneintrags deinstalliert nichts.

Spielstände und Mods liegen unter `profile/`. Vor einem Spiel- oder Proton-Update den Server stoppen und das Volume sichern; Updates werden per **Reinstall** ausgeführt.

## Image-Build

Der [GitHub-Workflow](https://github.com/DasEric/fs25-docker/actions/workflows/docker.yml) baut bei jedem Push ein Image und veröffentlicht es auf dem Standardbranch als `ghcr.io/daseric/fs25-docker:latest` und mit einem festen Tag pro Commit. Spiel und Produktschlüssel sind im Image nicht enthalten.
