# PI3TWE Rev D op de NUC

De interne relais K1/K2 en het externe vermogensrelais K3 worden uitsluitend door de print bestuurd. S2/S3 in het schema stellen twee externe USB-relaiscontacten voor.

## USB-bedrading bij het Rev D-profiel

USB-relais 2: COM naar J5.1 (ENABLE_LO), NO naar J5.2 (GND).
USB-relais 3: COM naar J5.3 (NUC_KEY), NO naar J5.4 (+5 V).
Gebruik alleen droge contacten. Geen externe spanning invoeren.

USB-relais 1 blijft de bestaande Power-functie bedienen. Als dit contact nog geen afzonderlijke voedingsschakeling bedient, kan het in serie met relais 2 in de J5.1/2-vrijgavelus worden opgenomen: J5.1 -> relais 1 COM/NO -> relais 2 COM/NO -> J5.2. Daarmee verbreekt Power uit de vrijgave ook direct in hardware. Schakel de zendervoeding niet rechtstreeks met het kleine USB-relais; het schema voorziet daarvoor K3.

USB-relais 4 blijft ongebruikt voor deze print. Bestaande bedrading moet eerst gecontroleerd worden; onderstaande updater gaat uit van deze mapping.

## Besturing

Bij Power aan en modus AAN blijft relais 2 gesloten, ook tussen uitzendingen. De print kan daardoor zelfstandig COR-doorvoer en PTT verzorgen. Bij Power uit, STANDBY, UIT of beëindigen van de SvxLink-supervisor opent relais 2. De print herhaalt dus niet zelfstandig wanneer de supervisor gestopt is.

SvxLink vraagt PTT aan via relais 3. Het profiel stelt NO_REPEAT=1 in: de lokale RX-audio gaat niet nogmaals via de NUC naar de zender. EchoLink en lokale aankondigingen blijven via de audio-uitgang beschikbaar. VOX blijft voorlopig ingesteld; dit detecteert spraak, geen stille draaggolf. I²C-COR vereist nog een adapter en hulpdienst.

De hardware-RX-route wordt niet stilgelegd tijdens nieuws of andere aankondigingen; ontvangeraudio kan daarbij optellen. De print heeft op J5 geen afzonderlijke RX-mute-ingang. Software alleen kan die prioriteit dus niet afdwingen.

## Installatie

    sudo python3 /home/erik/svxlink-dash-pi3twe-fork/install/update-pi3twe-revd-interface.py

De updater test eerst, maakt een backup, stopt de engine, installeert alleen de supervisor en het profiel /etc/pi3twe/interface-profile, en start de engine weer als die eerder actief was. Bij een mislukte installatie worden supervisor en profiel teruggezet. Hij installeert geen onafgeronde METAR-dashboardwijzigingen. AAN + Power aan geeft na herstart de hardware vrij; COR kan dan meteen PTT aanvragen.

## Test op dummyloads

1. Power uit: vrijgavecontact open, geen PTT bij COR of NUC-verzoek.
2. Power aan + AAN: relais 2 gesloten; zonder COR of aankondiging relais 3 open.
3. Ontvangstsignaal: RX-led/COR, hardwareaudio naar TX en RX-audio naar NUC.
4. Test call RPTR: relais 3 sluit en opent weer; relais 2 blijft gesloten.
5. STANDBY tijdens ontvangst: relais 2 opent; hardware-PTT wordt geblokkeerd.
6. AAN herstelt vrijgave; UIT stopt de engine en opent relais 2/3.
7. Audio afregelen: VR2 laag beginnen op de mic-ingang, VR3 NUC-audio en VR4 zenddeviatie controleren. Controleer dat RX-spraak één keer wordt doorgestuurd.
