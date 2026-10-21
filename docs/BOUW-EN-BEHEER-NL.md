# PI3TWE — bouw, herstel en beheer

Nederlandse handleiding voor SvxLink-Dash-V3.1 met PI3TWE-uitbreiding. Uitgave 21 oktober 2026. Repository: https://github.com/videobuff/SvxLink-Dash-V3.1. De testresultaten en hun grenzen staan afzonderlijk in HERBOUWCONTROLE-NL.md.

## 1. Wat wordt opgebouwd?

Deze fork combineert het dashboard van Chris Jackson G4NAB, SvxLink van Tobias Blömberg SM0SVX en de PI3TWE-bediening voor Power, bedrijfsmodus, identificatie, nieuws en METAR. Het dashboard gebruikt poort 5000. SvxLink draait als een aparte dienst; de USB-relais worden via een supervisor aangestuurd. Er is één dashboardproces, omdat dat ook de nieuwsplanner en relaisbewaking uitvoert.

De beschreven schone installatie richt zich op Debian GNU/Linux 13 (Trixie), amd64, met systemd. SvxLink is vastgezet op release 26.05.2, broncommit 595cf9bb3325be753d05b219bdd39feab6a22b33, en 16 kHz interne audio. De PI3TWE-plugin moet tegen diezelfde bouw worden gecompileerd. Een willekeurige andere engine of plugin overnemen is geen herstelprocedure.

De kale software-installatie en hardware-inbedrijfstelling zijn afzonderlijke stappen. USB-relaismodule QAAMZ, het Rev D-interfaceprofiel en ALSA-kaart 1 zijn de uitgangspunten. Controleer die op de nieuwe computer. De schone installer start geen diensten en schrijft modus UIT. De bestaande repeater wordt bij het maken van deze handleiding niet herstart of opnieuw geïnstalleerd.

SDR-ontvangst, MediaMTX, OpenWebRX, Apache, Grafana, Prometheus en APRS zijn aanvullende voorzieningen. Ze worden niet door de schone basisinstaller geïnstalleerd. De bijbehorende dashboardvelden kunnen dus onbeschikbaar melden totdat die diensten apart zijn ingericht.

## 2. Eerst veiligstellen bij vervanging van een bestaande computer

GitHub bevat broncode, voorbeelden, het Nederlandse geluidspakket en deze documentatie. GitHub bevat bewust geen EchoLink-wachtwoord, reflectorcode, dashboardaccount, database of eigen nieuwsbestanden. Zonder een aparte backup moet je die gegevens opnieuw invoeren.

Bewaar minimaal de volgende mappen op een afgeschermd medium:

- /opt/dashboard/config: het echte node_model.json, accounts en overige lokale modellen.
- /etc/pi3twe: actieve SvxLink-configuratie, module-instellingen en interfaceprofiel.
- /var/lib/pi3twe-svxdash: database, nieuws, bedrijfsmodus en sessiesleutel.
- /etc/systemd/system: eventuele lokale overrides voor audio, dashboard en engine.
- /etc/asound.conf en de opgeslagen ALSA-instellingen, indien aanwezig.
- Losse configuratie van stream, SDR, netwerk en monitoring, als die mee moet.

Plan onderhoud, zet de repeater op STANDBY of UIT en stop het dashboard vóór een eenvoudige bestandsbackup van de database. Dat voorkomt dat de SQLite-database tijdens het kopiëren wijzigt. Voor een online backup is de SQLite-backupfunctie nodig; kopieer niet alleen een open databasebestand en laat daarbij journal- of WAL-bestanden achter.

Voorbeeld voor een onderhoudsbackup:

```bash
sudo systemctl stop svxlink-dash.service pi3twe-svxlink.service
sudo tar -czf /root/pi3twe-herstelbackup.tar.gz \
  /opt/dashboard/config /etc/pi3twe /var/lib/pi3twe-svxdash
sudo chmod 600 /root/pi3twe-herstelbackup.tar.gz
```

Zet de backup op een ander medium. Start na het onderhoud alleen de diensten die vóór het onderhoud actief waren. Deze backup bevat geheimen; voeg hem niet toe aan Git.

## 3. Schone Debian-installatie voorbereiden

Installeer Debian 13 amd64 met een normale beheerder, sudo, netwerktoegang en de juiste tijd. Gebruik Europe/Amsterdam als tijdzone. Start met de radio-interface losgekoppeld. Voer de schone installer uitsluitend op een nieuwe machine of test-VM uit: hij weigert een al aanwezige /opt/dashboard of /etc/pi3twe.

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates sudo
sudo timedatectl set-timezone Europe/Amsterdam
git clone https://github.com/videobuff/SvxLink-Dash-V3.1.git
cd SvxLink-Dash-V3.1
git rev-parse HEAD
```

Noteer de commit waarmee je bouwt. Voor een latere identieke bronversie checkout je die commit. De Debian-pakketten en externe bronnen worden online opgehaald; dit is geen volledig offline image of bit-voor-bit reproduceerbare firmware.

```bash
sudo bash install/install-clean-debian13.sh
```

De installer installeert de pakketten uit install/build-deps.txt, bouwt de vastgezette SvxLink-bron onder /var/tmp/pi3twe-build, installeert hem onder /usr/local en bouwt de PI3TWE-plugin. Vervolgens kopieert hij dashboard, diensten, helpers, taalbestanden en een voorbeeldconfiguratie. Er is geen afhankelijkheid van een /home/erik-checkout of de oude PI3TWE-controller.

De optionele eerste parameter bepaalt de bouwmap:

```bash
sudo bash install/install-clean-debian13.sh /var/tmp/mijn-pi3twe-build
```

Als de bouw mislukt: lees de foutmelding en herstel die eerst. Voer niet de bestaande-hostmigratie uit om een mislukte schone installatie te omzeilen. De migratie verwacht een bestaande werkende PI3TWE-installatie en lokale data.

## 4. Bestanden en diensten controleren

Na de installatie verwacht je:

- /usr/local/bin/svxlink: de engine; --version toont 1.10.2@26.05.2.
- /usr/local/lib/pi3twe-svxlink/Pi3tweLogic.so: de eigen plugin.
- /usr/local/lib/pi3twe-svxlink/manifest.json: ABI-controle van engine en RepeaterLogic.
- /opt/dashboard: dashboardcode en lokale configuratie.
- /etc/pi3twe/svxlink/svxlink.conf en svxlink.d: bronconfiguratie.
- /usr/share/svxlink/sounds/nl_NL: Nederlandse clips en taalfuncties.
- /var/lib/pi3twe-svxdash: blijvende status, database en nieuws.
- svxlink-dash.service: dashboard en achtergrondtaken.
- pi3twe-svxlink.service: SvxLink-supervisor met relaisbrug.

```bash
/usr/local/bin/svxlink --version
sudo visudo -cf /etc/sudoers.d/svxlink-dash
sudo systemd-analyze verify \
  /etc/systemd/system/svxlink-dash.service \
  /etc/systemd/system/pi3twe-svxlink.service
```

De runtimeconfiguratie onder /run/pi3twe-svxlink wordt door de supervisor gegenereerd. Bewerk die niet als blijvende instelling. De supervisor dwingt de PTT-route via de lokale PTY af en gebruikt zijn eigen plugin.

## 5. Audio en USB-interface instellen

```bash
aplay -l
arecord -l
amixer -c 1 scontrols
usbrelay
```

Vergelijk de hardware met de uitgangspunten. Het dashboardvoorbeeld gebruikt alsa:plughw:1. Kaartnummering kan na een herstart veranderen; gebruik waar mogelijk een stabiele ALSA-kaartnaam. De helpers pi3twe-svxlink-audio-init en pi3twe-svxlink-check controleren momenteel expliciet kaart 1 en de mixerfunctie Loopback Mixing. Pas die beide aan als je andere audiohardware gebruikt en test opnieuw. Laat de analoge Mic/Loopback-route uit om terugkoppeling te voorkomen.

De relay-ID staat zowel in de systemd-omgeving van het dashboard als in install/pi3twe-svxlink-ptt. Bij een andere module-ID moeten die overeenkomen. Lees eerst usbrelay zonder een schakelopdracht te geven. De udev-regel voor de gebruikte 16c0:05df-module geeft de groep plugdev toegang; controleer het echte USB-type en herlaad de regels na wijzigingen.

Voor Rev D:

- Relais 1: bestaande Power-functie.
- Relais 2: hardwarevrijgave, J5.1 naar J5.2 via droog contact.
- Relais 3: NUC-PTT, J5.3 naar J5.4 via droog contact.
- Relais 4: ongebruikt bij deze print.

De gedetailleerde beschrijving staat in pi3twe-revd-interface.md. Het standaardprofiel van de schone installatie is revd. Verwijder /etc/pi3twe/interface-profile uitsluitend als je bewust de oudere relaisvolgorde wilt gebruiken. Dan gelden andere bedrading en softwarematige RX-doorvoer.

De Rev D-print verzorgt de lokale RX-doorvoer zelf; NO_REPEAT=1 voorkomt dubbele audio. Hardware-RX-audio kan tijdens een softwareaankondiging blijven optellen. De software heeft geen afzonderlijke RX-mute-lijn op deze interface.

## 6. Eerste start en dashboardaccount

Controleer de bronconfiguratie en voorbeeldinstellingen vóór de eerste engine-start. De installer heeft modus UIT vastgelegd. Start eerst alleen het dashboard:

```bash
sudo systemctl daemon-reload
sudo systemd-tmpfiles --create /etc/tmpfiles.d/pi3twe-svxdash.conf
sudo systemctl start svxlink-dash.service
```

Open http://IP-ADRES:5000/ op het lokale beheernetwerk. Maak het dashboardaccount aan wanneer Setup Authentication verschijnt. De voorbeeldconfiguratie bevat geen gedeeld standaardwachtwoord. Gebruik één dashboardproces; meerdere workers zouden elkaar bij de planning blokkeren.

Controleer roepletter, RX/TX-audioapparaat, CW, VOX/squelch, identificatie, modulekeuze en locatie. Het voorbeeld gebruikt PI3TWE; vervang dat voor een andere repeater. EchoLink en reflector zijn in de schone voorbeeldconfiguratie uitgeschakeld. Vul eigen accountgegevens in voordat je ze activeert.

De PI3TWE-statuspagina kan op een kale machine melden dat SDR of streaming niet aanwezig is. Dit verhindert op zichzelf geen basisconfiguratie van de engine, mits de streambronbewaking op sdr staat en de analoge audiolus uit is.

## 7. Locatie, taal en configuratiebuild

Gebruik voor de locatie decimale graden, met een punt:

- Breedtegraad/latitude: 52.116500.
- Lengtegraad/longitude: 6.662833.
- Noord en oost zijn positief; locator JO32JC.

Dit is de omzetting van 52°06.99′ N, 6°39.77′ E. Het is graden plus decimale minuten; deel de minuten door 60.

De blijvende taalkeuze is language.default = nl_NL in /opt/dashboard/config/node_model.json. De schone voorbeeldconfiguratie gebruikt die al. De build zoekt eerst naar het aanwezige taalpakket; voor Nederlands is geen aparte Engelse taalrepository nodig. Een wijziging van de omgevingsregio behoudt voortaan de gekozen spreektaal.

Rebuild betekent in het dashboard: configuratie opnieuw genereren. Het compileert niet de C++-engine. Handmatige wijzigingen in gegenereerde configuratie kunnen verdwijnen. Zet daarom blijvende waarden in het model of in de daarvoor bedoelde PI3TWE-instellingen.

Voor een bestaande installatie die nog Engels heeft: wijzig language.default naar nl_NL in het model, zorg dat het pakket aanwezig is en voer daarna Build Configuration uit. Controleer in svxlink.conf en, indien ingeschakeld, ModuleEchoLink.conf de regel DEFAULT_LANG=nl_NL. Herstart SvxLink op een geschikt onderhoudsmoment.

De footer toont afzonderlijk dashboardversie, Debian-pakketversie en engineversie. Bij deze broninstallatie is 'SvxLink Package handmatige installatie' normaal. De engineversie hoort 1.10.2@26.05.2 te zijn; 'unknown' vraagt nader onderzoek.

## 8. Inbedrijfstelling met gecontroleerde RF-test

Gebruik een geschikte testopstelling en dummyload. Met Rev D kan vrijgave onmiddellijk hardware-COR/PTT toestaan. Controleer de bedrading voordat je AAN en Power aan kiest.

1. Controleer bij Power uit dat de vrijgave en PTT open zijn.
2. Kies AAN met gecontroleerde hardware aangesloten. Controleer dat de engine gereed wordt.
3. Zet Power aan. Zonder ontvangst of aankondiging hoort er geen NUC-PTT te zijn.
4. Test ontvangst en controleer dat RX-spraak één keer doorkomt.
5. Gebruik Test call RPTR en controleer CW, niveau en het weer openen van PTT.
6. Test STANDBY tijdens ontvangst; de vrijgave moet openen.
7. Test een kort nieuwsbestand met passende niveaus.
8. Test de MetarInfo-module alleen als die geladen is en er een actueel bericht bestaat.
9. Herstart de computer en controleer modus, planning, audioapparaten en herstel.

Schakel automatisch starten pas na die controle in:

```bash
sudo systemctl enable svxlink-dash.service pi3twe-svxlink.service
```

UIT blijft als gewenste modus bewaard. Alleen enable uitvoeren heft UIT niet op. Kies via het dashboard bewust AAN wanneer je wilt dat de engine gaat draaien.

## 9. Dagelijks gebruik

Power bedient de fysieke Power-functie. AAN, STANDBY en UIT beschrijven de SvxLink-modus. In STANDBY blijft de engine met onder andere EchoLink-registratie beschikbaar, maar is de radiofunctie geblokkeerd. UIT stopt de engine en blijft bij een herstart bewaard. Alleen een groene dashboardpagina bewijst nog geen correcte RF-werking.

De PI3TWE-pagina heeft Test call RPTR en Test nieuws. Test call gebruikt de lokale repeateridentificatie en hoeft nieuws niet in te schakelen. Test nieuws zendt het geselecteerde bestand daadwerkelijk uit. Een luistervoorbeeld in de browser blijft alleen in de browser. Tijdens een uitzending blijven Power uit en STANDBY beschikbaar.

Upload nieuws als MP3, WAV, OGG, FLAC of M4A. Nieuwe bestanden staan eerst uit. Stel geldigheid in, activeer het bulletin en schakel Nieuws toegestaan in. De planner kiest in de eerste vijf minuten van elk uur het nieuwste geldige actieve bulletin. Oudere geldige bulletins worden daarbij overgeslagen. Hij wacht op het einde van de uuridentificatie, met een wachttijd van maximaal 90 seconden. Het gekozen bulletin wordt maximaal één keer per UTC-uur geclaimd. Upload daarom niet halverwege het uur alweer een nieuw actief bulletin als je een extra uitzending wilt voorkomen. Power, AAN en nieuwstoestemming moeten aanwezig zijn. Een gemist of mislukt slot wordt niet later in hetzelfde uur ingehaald. Handmatige tests omzeilen planning en geldigheidsperiode, maar vereisen nog steeds toestemming en normale radiofunctie.

De identificatie-instellingen blijven in de database bewaard en worden na een engineherstart opnieuw toegepast. Nieuws wordt zonder toegevoegde pieptonen afgespeeld, zoals op de huidige NUC. Oudere instellingen voor pieptonen blijven mogelijk in de database staan maar worden door deze nieuwsspeler niet gebruikt.

## 10. METAR en EchoLink

Kies vliegvelden met ICAO-codes van vier letters: bijvoorbeeld EDDG, EDLS of EHTW. Een geldige code garandeert geen beschikbaar weerbericht. De gesproken weergave komt van SvxLinks MetarInfo-module. Internet, een geladen module en het geconfigureerde vliegveld zijn vereist. Je kunt vliegvelden via MetarInfo bewerken; het standaardvliegveld en de extra ICAO-codes worden bij het bouwen meegenomen.

Een afzonderlijke experimentele PI3TWE-knop Test METAR is niet opgenomen in deze herstelversie. METAR via de reguliere SvxLink-module blijft beschikbaar. Gebruik daarvoor de ingestelde module-ID en de DTMF-selectie van het vliegveld. De standaard module-ID is 5; controleer de eigen configuratie vóór je commando's stuurt.

EchoLink gebruikt de eigen accountroepnaam, bijvoorbeeld een -R-roepnaam, en het eigen wachtwoord. Dat staat los van de lokale CW-identificatie. De lokale PI3TWE-identificatie voegt geen automatische /R toe. Publiceer geen EchoLink- of reflectorcredentials in GitHub of een supportlog.

## 11. Updates, tests en terugzetten

Werk in een checkout buiten /opt/dashboard en maak eerst een backup. Controleer release, lokale wijzigingen en het native ABI-manifest. Een nieuwe SvxLink-release vereist een bijpassende pluginbouw en tests; vervang niet alleen de executable.

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -v
git diff --check
```

De native test is bedoeld voor een reeds gebouwde engine en plugin. Hij start een aparte SvxLink met Dummy RX en Dummy TX; hij schakelt geen USB-relais:

```bash
python3 scripts/check-native-tests.py
```

Voor de bestaande PI3TWE-NUC is install/migrate-pi3twe-dashboard.py een afzonderlijke migratieroute met backups en rollback. Die is specifiek voor de bestaande installatiestructuur en gebruikersdiensten. Gebruik hem niet als universele nieuwe-hostinstaller.

Voor een herstel uit backup: installeer eerst dezelfde bronversie op een schone machine, houd de diensten gestopt, zet config en toestand terug en herstel eigenaar svxlink met groep audio. Controleer de audiokaart, relay-ID en sessiesleutel. Zet modus UIT of STANDBY vóór je de diensten start. Een hardwarewijziging vraagt opnieuw de controles uit hoofdstuk 8.

### Herbouwtest in een wegwerpcontainer

Met Docker op een aparte ontwikkelcomputer kun je de installatie en dummy-enginecontrole opnieuw uitvoeren. Dit bouwt een image; het start geen repeatercontainer of radio:

```bash
docker build -f tests/Dockerfile.debian13 -t pi3twe-herbouwtest .
```

De Dockerfile voert de schone installer uit, daarna de native Dummy RX/TX-test en scripts/check-clean-install.py. De laatste controle toetst onder meer Nederlands, de ABI-hashes, configuratie, sudoers, unitbestanden en modus UIT. Een geslaagde containerbouw vervangt geen hardware- en rebootcontrole op de uiteindelijke machine.

## 12. Storingen herkennen

Bij een dashboardfout:

```bash
sudo systemctl status svxlink-dash.service --no-pager
sudo journalctl -u svxlink-dash.service -n 100 --no-pager
```

Bij een engine- of audiofout:

```bash
sudo systemctl status pi3twe-svxlink.service --no-pager
sudo journalctl -u pi3twe-svxlink.service -n 100 --no-pager
sudo tail -n 100 /var/log/pi3twe-svxlink/svxlink.log
```

'Native engine niet gereed' kan wijzen op ontbrekende libraries, een verkeerde plugin, ontbrekende eventbestanden of ongeldige configuratie. Gebruik de complete 26.05.2-eventbestanden; meng ze niet met oudere Debian 24.02-bestanden. Controleer LD_LIBRARY_PATH en het ABI-manifest.

'Analoge uitgang niet in zendmodus' vraagt controle van Loopback Mixing, Mic-mute en kaartnummer. 'Microfooningang is al de publieke streambron' betekent dat de bronbewaking de engine blokkeert. Start geen analoge streamdienst die dezelfde microfoonroute gebruikt terwijl SvxLink die bezit.

Een uitgeschakelde testknop vraagt controle van Power, AAN, native gereedheid, huidige uitzending, geselecteerd bestand/vliegveld en modulebeschikbaarheid. Lees de gebeurtenislijst voordat je herhaaldelijk opnieuw test.

## 13. Documentatie opnieuw als PDF maken

De Markdown-bestanden zijn de bewerkbare bron. De PDF-generator gebruikt ReportLab en het DejaVu-lettertype uit Debian. Installeer de documentafhankelijkheden in een virtuele omgeving:

```bash
sudo apt-get install -y python3-venv fonts-dejavu-core
python3 -m venv .venv-docs
.venv-docs/bin/pip install -r docs/requirements.txt
.venv-docs/bin/python scripts/build-manuals.py
```

De drie PDF's komen in docs/pdf. Voeg na inhoudelijke wijzigingen zowel de bron als de nieuwe PDF toe aan Git. Raadpleeg HERBOUWCONTROLE-NL.md voor wat in deze uitgave daadwerkelijk is gecontroleerd.
