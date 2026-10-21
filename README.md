# SvxLink-Dash — PI3TWE

PI3TWE-uitbreiding van [SvxLink-Dash-V3.1 van Chris Jackson G4NAB](https://github.com/f5vmr/SvxLink-Dash-V3.1), met [SvxLink van Tobias Blömberg SM0SVX](https://github.com/sm0svx/svxlink). De oorspronkelijke Git-geschiedenis en auteursvermeldingen zijn behouden.

Deze fork combineert het configuratiedashboard met Power, AAN/STANDBY/UIT,
identificatie, nieuwsupload en nieuwsplanning voor de PI3TWE-repeater.
Het dashboard draait op poort **5000**; SvxLink en de USB-relaisbrug draaien
onder een afzonderlijke systemd-dienst.

## Nederlandse handleidingen

- [Bouw, herstel en beheer](docs/BOUW-EN-BEHEER-NL.md) — [PDF, 7 pagina's](docs/pdf/BOUW-EN-BEHEER-NL.pdf).
- [Korte gebruikerskaart](docs/GEBRUIKERSKAART-NL.md) — [PDF, 1 pagina](docs/pdf/GEBRUIKERSKAART-NL.pdf).
- [Herbouwcontrole en testgrenzen](docs/HERBOUWCONTROLE-NL.md) — [PDF](docs/pdf/HERBOUWCONTROLE-NL.pdf).
- [Rev D-interface en relaisbedrading](docs/pi3twe-revd-interface.md).
- [Bestaande-hostmigratie en technische achtergrond](docs/PI3TWE.md).

## Installatie op een schone machine

Doelplatform: **Debian 13 amd64 met systemd**. Engine: **SvxLink 26.05.2**,
16 kHz interne audio. De bouw haalt de vastgezette upstream-commit op en
compileert de PI3TWE-plugin tegen dezelfde engine.

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates sudo
git clone https://github.com/videobuff/SvxLink-Dash-V3.1.git
cd SvxLink-Dash-V3.1
sudo bash install/install-clean-debian13.sh
```

Alleen voor een nieuwe host. De installer weigert een bestaande
`/opt/dashboard` of `/etc/pi3twe`. Hij start geen diensten en laat de modus op
**UIT**. Controleer vóór inbedrijfstelling audiokaart, relay-ID, bedrading,
roepnaam, locatie en eigen accounts volgens de bouw- en beheerhandleiding.

Het meegeleverde profiel gebruikt de Rev D-interface, USB-relais QAAMZ en
ALSA-kaart 1. Andere hardware vereist aanpassing. De reguliere MetarInfo-module
is beschikbaar; de nog niet uitgerolde experimentele PI3TWE-METAR-testknop is
niet opgenomen in deze herstelversie.

Het Nederlandse geluidspakket staat met checksum in `assets/nl_NL.tar.xz`.
De taalkeuze `nl_NL` blijft behouden bij configuratiebuilds en regiowijzigingen.
Nieuws speelt zonder toegevoegde pieptonen; de planner kiest het nieuwste
geldige actieve bulletin en wacht kort op de uuridentificatie.

**Hersteldata:** wachtwoorden, dashboardaccount, database en eigen
nieuwsbestanden staan bewust niet in Git. Bewaar die in een aparte backup.
SDR-stream, MediaMTX, OpenWebRX en monitoring zijn aanvullende voorzieningen en
worden niet door de basisinstaller geïnstalleerd.

## Controle van de bouw

Met Docker op een ontwikkelmachine:

```bash
docker build -f tests/Dockerfile.debian13 -t pi3twe-herbouwtest .
```

Dit bouwt de software in Debian 13 en controleert de installatie,
configuratierebuild en native engine met Dummy RX/TX. Het start geen radio.
De daadwerkelijk uitgevoerde controles en beperkingen staan in het
[herbouwverslag](docs/HERBOUWCONTROLE-NL.md).

Python-tests op een machine met de afhankelijkheden uit `install/build-deps.txt`:

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -v
git diff --check
```

## Bestaande PI3TWE-installatie

Gebruik de schone installer niet voor een update van de werkende NUC.
`install/migrate-pi3twe-dashboard.py` is een afzonderlijke, hostspecifieke
migratieroute met backups en rollback. Lees eerst de migratienotities en maak
een backup. Een update van SvxLink vereist een passende native plugin en tests.

## Documentatie bouwen

De bewerkbare bronnen staan in `docs/*.md`. PDF's worden gegenereerd met
`python scripts/build-manuals.py`, ReportLab uit `docs/requirements.txt` en
Debians DejaVu-lettertypen. Zie de uitgebreide handleiding voor de commando's.

De [oorspronkelijke upstream-README](docs/UPSTREAM-README.md) is bewaard als
achtergrond. De daarin beschreven generieke upstream-installer is niet de
installatieprocedure voor deze PI3TWE-fork.
