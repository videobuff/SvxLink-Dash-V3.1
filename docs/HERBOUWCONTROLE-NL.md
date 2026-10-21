# PI3TWE — herbouwcontrole

Controleverslag, 21 oktober 2026. Dit document hoort bij de Nederlandse bouw- en beheerhandleiding en de korte gebruikerskaart in deze repository.

## Doel en afbakening

De vraag is of de PI3TWE-repeatercontroller met de gegevens in GitHub op een schone Linux-machine opnieuw kan worden opgebouwd. De ondersteunde basis voor deze uitgave is Debian 13 amd64. Een andere distributie of processorarchitectuur is hiermee niet automatisch getest.

Broncode en openbare herstelassets staan in Git. Lokale accountgegevens, EchoLink- en reflectorwachtwoorden, eigen nieuwsbestanden en de operationele database horen in een aparte backup. Git alleen kan die lokale gegevens niet terughalen.

De herstelversie bevat de werkende nieuws- en CW-aanpassingen van de NUC. De nog niet uitgerolde experimentele METAR-testknop uit de ontwikkelwerkkopie is niet meegenomen. De reguliere MetarInfo-module en de bestaande ICAO-configuratie blijven beschikbaar.

## Gevonden herstelproblemen en correcties

- De oude NUC-installer veronderstelde een bestaande configuratie, gebruiker, stage-installatie en oude controller. Er is nu een afzonderlijke schone Debian 13-installer.
- De engine en plugin waren alleen vanuit lokale stagingmappen bouwbaar. De enginebouw haalt nu een vastgezette openbare SvxLink-commit op; de pluginbouw gebruikt systeemheaders en de actuele multiarch-map.
- De Nederlandse spraakbestanden stonden alleen op de lokale computer. Het volledige gebruikte pakket staat nu met checksum in assets/nl_NL.tar.xz.
- Rebuild accepteerde uitsluitend talen met een ingestelde externe taalrepository. Een aanwezig lokaal taalpakket wordt nu eerst herkend.
- De omgevingsregio overschreef de spreektaal. De gekozen taal blijft nu behouden.
- De renderer las sjablonen altijd uit /opt/dashboard, ook vanuit een broncheckout. Hij gebruikt nu de sjablonen uit zijn eigen checkout.
- Een minimale beheeromgeving had geen bruikbaar zoekpad voor groupadd/useradd. De installer neemt passwd expliciet op en zet de beheer-PATH vast.
- De footer zocht alleen /usr/bin/svxlink. Hij herkent nu ook de broninstallatie in /usr/local/bin en vermeldt een handmatige installatie wanneer het Debian-pakket ontbreekt.
- Enkele live aanpassingen stonden nog niet in Git: nieuws zonder piepen, selectie van het nieuwste geldige bulletin, wachten op de uuridentificatie, een directe CW-menukeuze en CPM/WPM-weergave. Deze zijn in de herstelbron opgenomen.

## Uitgevoerde controles

De Python-tests zijn uitgevoerd met ResourceWarning als fout. De stabiele herstelbron doorstaat 74 tests, waaronder taalbehoud, het Nederlandse voorbeeldmodel, Power/STANDBY, authenticatie, nieuwsverwerking zonder extra tonen, uuridentificatie en de keuze van het nieuwste bulletin.

De native plugin is lokaal opnieuw gecompileerd tegen SvxLink 26.05.2. De aparte native test gebruikt Dummy RX en Dummy TX en controleert Power-blokkering, gelijktijdige opdrachten, argumentcontrole, annuleren, afronden van de repeateridentificatie en nieuws na een call-test. Er worden geen echte USB-relais aangestuurd.

De schone bouw wordt gecontroleerd in een apart Debian 13 amd64-rootfilesystem, afkomstig van het officiële Debian slim-image. De bron van het image staat op https://github.com/debuerreotype/docker-debian-artifacts. Het gebruikte rootfilesystem heeft SHA-256 f2be67225471500c788ce88c597eb5ea8336e912ad1ca4815650e0281afe2034.

De testomgeving is met PRoot ingericht, omdat Docker op de beheerhost zonder beheerderswachtwoord niet toegankelijk is. De C++-bouw wordt daarna in een gebruikersnamespace met chroot voortgezet om de PRoot-overhead te vermijden. PRoot is geen opgestart systeem met systemd. Alleen binnen de testomgeving wordt systemd-tmpfiles tijdens de pakketinstallatie overgeslagen wegens een PRoot-incompatibiliteit; automatisch starten van diensten is eveneens geblokkeerd. Dit is geen wijziging in de productie-installer.

Resultaat: GESLAAGD. De vastgezette SvxLink-bron is in deze schone omgeving gecompileerd en geïnstalleerd; daarna is de native PI3TWE-plugin tegen dezelfde bouw gecompileerd. De provisioning en controles zijn achtereenvolgens uitgevoerd:

- Alle 74 Python-tests geslaagd binnen de schone Debian-omgeving.
- Dashboard, helpers, configuratie en het Nederlandse geluidspakket geïnstalleerd.
- Volledige configuratierebuild zonder serviceherstart geslaagd; DEFAULT_LANG bleef nl_NL.
- Engineversie 1.10.2@26.05.2 en beide ABI-hashes gecontroleerd.
- Moduleconfiguratie, lokale eventbestanden en sudoers gecontroleerd.
- Beide systemd-unitbestanden met systemd-analyze verify gecontroleerd.
- Modus UIT aanwezig; geen dashboard- of repeaterdienst automatisch ingeschakeld.
- Native CALL/NEWS-controle met Dummy RX en Dummy TX geslaagd in de schone omgeving.

De installatie is in fases getest: pakketinstallatie en provisioning met PRoot, de engine- en pluginbouw in een gebruikersnamespace. De meegeleverde Dockerfile voert deze stappen in één containerbouw achter elkaar uit. Die Docker-run zelf is hier niet uitgevoerd, omdat toegang tot de Docker-daemon ontbrak. Een echte systemd-boot of RF-uitzending maakt geen deel uit van dit testresultaat.

## Wat deze controle niet bewijst

Een softwarebouw en Dummy RX/TX-test bewijzen niet dat COR, PTT, audiolevels en zenddeviatie op een nieuw aangesloten interfacebord correct zijn. Ook een echte reboot, USB-apparaatnamen, fysieke vrijgave en het terugzetten van privéaccounts moeten op de uiteindelijke machine worden gecontroleerd.

De schone basisinstallatie omvat geen SDR-stream, MediaMTX, OpenWebRX, Apache, Grafana, Prometheus of APRS. Als die voorzieningen nodig zijn, zijn aanvullende configuratie en een backup nodig. Een foutmelding bij die optionele velden is geen bewijs dat de basisengine niet kan worden gebouwd.

De build gebruikt online Debian-pakketten en een vastgezette SvxLink-broncommit. Dit is een herhaalbare bronprocedure, geen offline herstelimage of garantie op byte-identieke binaries. Voor offline herstel moet je bovendien pakketten en bronarchives veiligstellen.

## Controle opnieuw uitvoeren

Op een computer met Docker:

```bash
git clone https://github.com/videobuff/SvxLink-Dash-V3.1.git
cd SvxLink-Dash-V3.1
docker build -f tests/Dockerfile.debian13 -t pi3twe-herbouwtest .
```

Voor alleen de Python-tests op een ontwikkelmachine met de genoemde afhankelijkheden:

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -v
git diff --check
```

Voor hardware-inbedrijfstelling volg je hoofdstuk 8 van BOUW-EN-BEHEER-NL.pdf. Noteer de Git-commit en de uitkomst van die controles bij de backup van de installatie.
