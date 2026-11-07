# Farming Simulator 25 für Pterodactyl

Eigenes Linux/amd64-Image und Pterodactyl-Egg nach der FS25-Vorlage von [CubeCoders AMP](https://github.com/CubeCoders/AMPTemplates). Die Installation verwendet den offiziellen GIANTS-Download und GE-Proton, nicht SteamCMD. Du brauchst einen eigenen GIANTS-Produktschlüssel für den Server und etwa **70 GiB freien Speicher** für die Erstinstallation. Das Disklimit im Panel muss dafür ausreichen.

## Installation

1. Nach dem ersten erfolgreichen Build auf dem Standardbranch unter **Actions → Build FS25 images** das Artefakt `farming-simulator-25-egg` herunterladen und entpacken. Alternativ im [Egg aus dem Repo](egg-farming-simulator-25.json) beide `ghcr.io/your-org/your-repo`-Pfade ersetzen. Das GHCR-Paket muss für Wings lesbar sein (öffentlich oder mit Registry-Zugang).
2. Die JSON-Datei im Pterodactyl-Adminbereich als Egg importieren und einen Server anlegen. Standard-Allocations: **10823/UDP** als Hauptport, **8080/TCP** fürs Webinterface, bei TLS zusätzlich **8443/TCP**. Abweichende Webports in den Egg-Variablen an die Allocations anpassen.
3. Nach dem ersten Installationslauf als Node-Admin im Servervolume `.fs25-secrets/activation-key` anlegen: eine Zeile mit dem Schlüssel, Dateimodus `0600`, Eigentümer wie das Servervolume. Optional dort `web-admin-password` setzen; sonst steht das von FS25 erzeugte Passwort in `game/dedicatedServer.xml`. Produktschlüssel und Passwörter gehören nicht in die Egg-Variablen.
4. Im Panel **Reinstall** auslösen und nach Abschluss starten. Die GIANTS-Oberfläche ist standardmäßig unter `http://NODE-IP:8080` erreichbar. Für TLS `game/cert.pem` und `game/pk.pem` bereitstellen und TLS im Egg einschalten.

Optionale Dateien im gleichen Format: `download-url` (offizieller GIANTS-`.img`-Link), `game-password` und `ingame-admin-password`.

Spielstände und Mods liegen unter `profile/`. Vor einem Spiel- oder Proton-Update den Server stoppen und das Volume sichern; Updates werden per **Reinstall** ausgeführt.

## Image-Build

GitHub Actions baut beide Images bei jedem Push. Auf dem Standardbranch veröffentlicht der Workflow `ghcr.io/OWNER/REPO:latest` und `:installer` sowie feste Tags pro Commit. Spiel und Produktschlüssel sind in keinem Image enthalten.
