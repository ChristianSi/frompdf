# Interaktives Anpassungsfähiges E-Learning-System Im

# Bereich Datenbanken

#### Fabian Keller Hochschule Harz Friedrichstraße 57-59 38855 Wernigerode fkeller@hs-harz.de

#### Pia-Katharina Habekost Hochschule Harz Friedrichstraße 57-59 38855 Wernigerode u36775@hs-harz.de

#### Kerstin Schneider Hochschule Harz Friedrichstraße 57-59 38855 Wernigerode kschneider@hs-harz.de

## ABSTRACT

Das E-Learning-System ALEA [4] wird im Bereich Da-
tenbanken entwickelt, weiterentwickelt und eingesetzt. Es
besteht aus verschiedenen Komponenten, die unterschied-
liche Teilgebiete adressieren. Diese sollen weitestgehend mit
den Lernenden interagieren und Hilfestellungen bereitstel-
len. Die typischerweise in einfuhrenden Datenbanklehrver- ¨
anstaltungen enthaltenen Aufgaben in den Bereichen ER-
to-Relational-Mapping und Normalisierung sind in der Re-
gel sehr aufwendig zu korrigieren. Fur die Lernenden ist ein ¨
Uben dieser Aufgaben jedoch sehr hilfreich. F ¨ ur das ALEA- ¨
System wurden daher interaktive Komponenten fur die bei- ¨
den Bereiche entwickelt und genutzt.

E-Learning-Systeme finden immer weitere Verbreitung in
den verschiedensten Lehrbereichen. Auch im Bereich Da-
tenbanken gibt es eine Vielzahl von Anwendungsgebieten.
Es werden zwei Komponenten vorgestellt, die bei der Leh-
re im Rahmen von Aufgaben bezogen auf ER-to-Relational-
Mapping und Normalisierung unterstutzen sollen. Vielf ¨ ¨altige
Interaktionen und Hilfestellungen bspw. Empfehlungen von
multimedialen digitalen Elementen werden zur Verbesserung
des Lernprozesses integriert.

## Keywords

Diese Komponenten und deren vielf¨altige Interaktions-
m¨oglichkeiten werden im Folgenden thematisiert. Grund-

E-Learning-Systeme, ER-to-Relational-Mapping, SQL-DDL,
Normalisierung, Recommender-Systeme

s¨atzliche M¨oglichkeiten zur Interaktion des E-Learning-Systems
werden hierbei veranschaulicht.

Nach einer kurzen Einfuhrung in die grundlegenden Aspek- ¨
te des Systems wird auf die Mapping-Aufgaben aus dem
Bereich ER-to-Relational-Mapping eingegangen. Die vielf¨al-
tigen Arten der Interaktionen bei der Bearbeitung werden
erl¨autert. Die Bearbeitung der Normalisierungsaufgaben er-
fordert erg¨anzende Interaktionsm¨oglichkeiten und Ansich-
ten, die im folgenden Kapitel beschrieben werden. Schließ-
lich werden die Ergebnisse zusammengefasst und ein Aus-
blick gegeben.

## 1. EINLEITUNG

Der Einsatz von E-Learning-Systemen wird zunehmend
bedeutsamer. Durch Erweiterungen der Interaktions- und

Feedbackm¨oglichkeiten kann die Nutzlichkeit der E-Learning- ¨
Systeme verbessert werden und den Lernenden nicht nur
in Selbstlernphasen Hilfestellungen und Unterstutzungsm ¨ ¨og-
lichkeiten im Lernprozess zur Verfugung stellen. Im Kon- ¨
text von Leistungsermittlungen k¨onnen Hilfestellungen ein-
geschr¨ankt werden, trotzdem sollen die Korrektur- und Ab-
fragem¨oglichkeiten erleichtert und verbessert sein.

## 2. GRUNDLEGENDE ASPEKTE

Das Konzept ER-to-Relational-Mapping und die Norma-
lisierung eines Relationenmodells bzw. relationalen Daten-

Das ALEA-System ist ein datenbankbasiertes E-Learning-
System fur Datenbanken und besteht aus verschiedenen Kom- ¨
ponenten fur unterschiedliche Bereiche. ¨

modells sind zwei grunds¨atzliche Gebiete, die in einfuhren- ¨
den Lehrveranstaltung im Bereich Datenbanken behandelt
werden. In den letzten Jahren wurden verst¨arkt E-Learning-
Syteme eingesetzt, sodass auch diese Gebiete von diesen Sys-
temen unterstutzt werden sollten. Das E-Learning Daten- ¨
bank Portal edb-Portal der TH K¨oln [3] ist ein umfangrei-
ches E-Learning-Angebot fur den Bereich Datenbanken und ¨
enth¨alt auch einen ER-Trainer. An der TU Munchen gibt es ¨
den DB-Normalizer [1].

Das System wurde haupts¨achlich mit Java und JavaS-
cript entwickelt. Als Entwurfsmuster wurde MVC2 verwen-
det, das heißt, es gibt eine logische Trennung zwischen Logik
und Anzeige. Die Anzeige basiert auf HTML5 in Kombina-
tion mit CSS und wurde mit JavaScript erweitert, um die
Interaktionsm¨oglichkeiten zu erh¨ohen und verbessern. Mit-
hilfe von AJAX werden nach Bedarf Daten an den Server
gesendet ohne dass die Webseite neu geladen wird. Zur Ver-
waltung der Information uber Aufgaben, L ¨ ¨osungen, Lernen-
de usw. werden Datenbanksysteme eingebunden.

## 3. AUFGABENTYP ER-TO-RELATIONAL- MAPPING

32nd GI-Workshop on Foundations of Databases (Grundlagen von Daten-
banken), September 01-03, 2021, Munich, Germany.

Fur die Thematik des ER-to-Relational-Mapping ist ein ¨
Fragentyp vorgesehen, der das Thema der Erstellung von
relationalen Datenmodellen beinhaltet auf Basis vorgegebe-

Copyright © 2021 for this paper by its authors. Use permitted under Crea-
tive Commons License Attribution 4.0 International (CC BY 4.0).

ner ER-Modelle und Anforderungen. Aufgaben dieses Typs
beinhalten die Darstellung eines konzeptuellen Datenmo-
dells, welche als Bild vorliegt, bspw. ein gezeichnetes ERM
in Chen-Notation [2]. Dieses soll von den Lernenden auf ein
logisches Datenmodell, hier ein Relationenmodell, abgebil-
det werden. Dazu sollen die Lernenden die entsprechenden
Tabellen und Constraints definieren. Die relevanten Cons-
traints sind Not Null, Unique, Primary Key und Foreign
Key.

#### Figure 2: Beispiel von Constraints

Die Mapping-Aufgaben sind darauf ausgelegt den Lernen-
den visuell und interaktiv Wissen zu vermitteln. In diesem
Fall fungiert das System als sog. Composer zur Erstellung

lisiert werden. Diese beziehen sich auf grunds¨atzliche Struk-
turen und Regeln bei den Tabellendefinitionen. Weiterhin
kann der ¨aquivalente DDL-Code aus den entstandenen Re-
lationen erzeugt werden, um eine Prufung auf dem Daten- ¨
bankserver auszufuhren. Dar ¨ uber hinaus k ¨ ¨onnen durch die
in der Datenbank zu der Aufgabe hinterlegten Informatio-
nen weitere Prufungen durchgef ¨ uhrt werden, die sich dar- ¨
uber hinaus speziell auf die Aufgabe und deren Anforde- ¨
rungen beziehen. Die Korrektheit einer L¨osung kann zwar
generell nicht automatisch entschieden werden, aber Fehler
k¨onnen weitestgehend erkannt werden. Die Gestaltung der
Aufgaben kann dies erleichtern.

der notwendigen Tabellen. In diesen k¨onnen durch Schalt-
fl¨achen Tabellenbezeichnung, Spalten und Constraints hin-
zugefugt werden. ¨

## 3.1 Bearbeitung der Aufgaben

Zur L¨osung der Mapping-Aufgaben gibt es fur jede Akti- ¨
on eine entsprechende Schaltfl¨ache. Das System erlaubt es
den Lernenden nicht mehrere Aktionen parallel auszufuhren. ¨
Erst nachdem eine Aktion abgeschlossen ist, kann eine neue
gestartet werden. Fur diesen Zweck werden alle anderen Ak- ¨
tionen durch das Deaktivieren der entsprechenden Buttons
unterbunden (siehe Abbildung 1). Wird zum Beispiel eine
neue Tabelle definiert, so muss fur die Tabelle ein Name ¨
eingegeben werden, bevor Spalten hinzugefugt werden k ¨ ¨on-
nen. Wiederum muss mindestens eine Spalte zu einer Tabel-
le geh¨oren damit Constraints erzeugt werden k¨onnen (siehe
Abbildung 2).

Bereits bei der Eingabe sind ausgew¨ahlte Strukturen und
Regeln bezogen auf die Tabellen und Constraints einzuhal-
ten, sodass diese idealerweise von den Studierenden verin-
nerlicht werden.

Der Composer fungiert grundlegend als dynamisch erweiter-
bares HTML-Formular. Die durch die Lernenden ausgel¨os-
ten Aktionen durchlaufen in dieser Phase nicht jedes Mal
eine Validierungsroutine auf dem Server, wodurch Ressour-
cen gespart werden.

Das konzeptuelle Datenmodell ist in den Aufgabenstellun-
gen als Bild enthalten. Dieses kann im oberen Bereich des
Systems eingeblendet werden. Damit die Lernenden zu je-
der Zeit einen freien Blick auf das abzubildende ER-Modell
haben, l¨asst sich dieses durch einen Klick in einem frei be-
weglichen modalen Fenster oder einem neuen Tab ¨offnen.
So besteht die M¨oglichkeit auch bei gr¨oßeren Datenmodel-
len, bei deren Verarbeitung vermehrt gescrollt werden muss,
den Uberblick zu behalten. Zudem kann die Gr ¨ ¨oße des ab-
gekoppelten Fensters durch Ziehen mit der Maus ver¨andert
werden.

Nicht alle logischen Zusammenh¨ange mussen durch das ¨
eingebundene Datenbanksystem gepruft werden. Ein Bei- ¨
spiel fur diese Art der Pr ¨ ufung ist die L ¨ ¨oschung von Spal-
ten. Durch eine Routine innerhalb der JavaScript-Skripte
wird gepruft, ob die Spalte f ¨ ur Constraints der aktuellen ¨
oder anderer Tabellen genutzt wird. Ist dies der Fall, gibt
das System eine Meldung aus und der L¨oschvorgang wird
abgebrochen. Die Umbenennung einer Spalte wird ebenfalls
durch eine JavaScript-Routine gepruft. Dieser Vorgang wird ¨
jedoch innerhalb der aktuellen Tabelle zugelassen und ein
Hinweis ausgegeben der darauf hinweist, dass andere Ta-
bellen mit dieser Spalte in Zusammenhang stehen k¨onnten,
sodass eine manuelle Prufung notwendig ist. Die durch die ¨
Anderung des Spaltennamens notwendigen Anpassungen in- ¨
nerhalb der Tabellendefinition werden automatisch durchge-
fuhrt. Da diese ¨ Anderungen die Lernenden von relevanteren ¨
Aspekten ablenken wurden. ¨

Das Zulassen von Aktionen trotz Inkonsistenz kann sinn-
voll sein. Ein Beispiel ist ein Fremdschlussel-Constraint, wel- ¨
cher angelegt wird bevor die referenzierten Spalten als Kan-
didatenschlussel (Primary Key oder NOT NULL/Unique ¨
Constraints) definiert wurden. Ansonsten wurden positive ¨
Aktionen zu stark von erzwungenen Reihenfolgeabh¨angig-
keiten gest¨ort werden. Die Lernenden k¨onnen jederzeit den
dem aktuellen Zustand entsprechenden DDL-Code uber das ¨
Datenbanksystem prufen lassen. F ¨ ur Leistungsbewertungen ¨
kann diese M¨oglichkeit eingeschr¨ankt werden.

#### Figure 1: Aktive Bearbeitung einer Spalte

## 3.2 Prüfen der Eingaben

## 3.3 Reaktionen des Systems auf Eingaben

Ein wichtiger Aspekt der Mapping-Aufgaben ist es die
Eingaben der Lernenden so fruh und umfangreich wie sinn- ¨
voll und m¨oglich zu prufen. Bereits bei den Eingaben werden ¨
clientseitige Abfragen genutzt, welche durch JavaScript rea-

Jede Aktion ruft eine Reaktion hervor. Wenn die Lernen-
den als Beispiel eine Spalte umbenennen, werden die Fol-
gen dieser Aktion in einer Meldung visuell dargestellt, da

ggfs. Anpassungen aufgrund von Abh¨angigkeiten in anderen
Tabellen durch die Lernenden notwendig werden k¨onnen.
Hierbei wird angestrebt, dass diese Meldungen motivierend
und angepasst an die Sprache der Lernenden formuliert wer-
den. Die Meldungstexte k¨onnen im System angepasst wer-
den. Hier bieten sich weitere M¨oglichkeiten fur intelligente ¨
Empfehlungsfunktionen. Die Lernenden durfen und sollen ¨
Fehler machen aus denen sie lernen k¨onnen. Das Wissen soll
sich durch Wiederholen verfestigen.

weiterfuhrende Informationen, so k ¨ ¨onnen diese in verschie-
denen medialen Formen, z.B. Screencasts, Podcasts, Hilfe-
texte, Hilfegrafiken, vorliegen und abgerufen werden.

Die Farbe der Icons kann, wie auch die Ansprache oder
empfohlene Medien, durch die Empfehlungsalgorithmen an-
gepasst werden.

Neben diesen Hinweisen werden zudem noch Informatio-
nen zum aktuellen Bearbeitungsstand der Aufgabe gegeben.
Diese Informationen finden die Lernenden unter dem Info-
Icon (siehe Abbildung 5).

Fur die Mapping-Aufgaben sind diese Hinweise vorteil- ¨
haft, um die Ubersicht ¨ uber den aktuellen Bearbeitungs- ¨
stand zu erhalten. Die Hinweise zeigen m¨ogliche Komplika-
tionen auf und sollen so das Verst¨andnis der Lernenden fur ¨
logische Zusammenh¨ange innerhalb des Relationenmodells
erh¨ohen. Deswegen kann es hilfreich, dass in den Hinweisen
angezeigt wird, dass Anderungen in der aktuellen Tabelle ¨
durchaus Auswirkungen auf die Constraints anderer Tabel-
len haben k¨onnten. So sind die Lernenden angehalten diese
aktiv anzupassen.

Wenn bspw. die L¨osung bzw. die gultigen L ¨ ¨osungen der
Aufgabe eine bestimmte Anzahl an Uniques erfordern oder
eine minimale oder maximale Anzahl an Uniques enthal-
ten durfen, kann den Lernenden mitgeteilt werden, dass die ¨
Anzahl der Uniques noch nicht einer gultigen L ¨ ¨osung ent-
spricht. Hierbei wird den Lernenden in der Regel keine kon-
krete Anzahl genannt, lediglich dass diese noch nicht gultig ¨
ist.

Zudem k¨onnen hier Hilfetexte erscheinen, die sich auf die
Arbeitsweise der Lernenden beziehen. Bemerkt das System
z.B. dass es im Bereich der Foreign Key Constraints zu
vermehrten Interaktionen kommt, k¨onnen hier Definitionen
oder Tipps zum Thema Foreign Key Constraints angezeigt
werden. Dies ist abh¨angig von den eingesetzten hybriden
Filter- und Empfehlungsalgorithmen.

Die eben genannten Hinweise erscheinen als modale Fens-
ter mittig in der Browserausgabe, um die Aufmerksamkeit
der Lernenden einzufangen und die Wichtigkeit dieser An- ¨
derung in den Vordergrund zu stellen (siehe Abbildung 3).
Diese Hinweise sollen w¨ahrend der Bearbeitung der Aufga-
be weiterhin zur Verfugung stehen und werden deshalb als ¨
zeitlich sortierte Liste abrufbar uber ein ’Notification Icon’ ¨
bereitgestellt. Eine Aufteilung der Listen in unterschiedli-
che thematische Listen wird nach weiteren Evaluierungen
entschieden. Diejenigen Nachrichten, die seit dem letzten
Offnen der Liste durch die Lernenden hinzugekommen sind, ¨
werden farblich hervorgehoben.

Um den Lernenden eine sog. ’Quick View’ uber den aktuel- ¨
len Bearbeitungsstand zu geben, befinden sich in der Toolbar
kleine Icons, welche repr¨asentativ fur Elemente der Model- ¨
lierung stehen. Dies sind von links nach rechts die Gesamtan-
zahl der aktiven Tabellen, der aktiven Spalten, der Primary
Key Constraints, der Unique Constraints, der Foreign Key
Constraints und der NOT NULLs außerhalb von Primary
Key Constraints (siehe Abbildung 4). Durch die Ubersicht ¨
der aktuell aktiven Elemente sollen die Lernenden eine kom-
pakte Ubersicht ¨ uber den aktuellen Zustand erhalten. Insbe- ¨
sondere in Ubungsphasen, in denen die Mindestanzahl oder ¨
die exakte Anzahl der ben¨otigten Elemente vorgegeben sein
kann, ist diese Ansicht hilfreich um zu eruieren, wie weit
sich das eigene Ergebnis vom gesuchten zumindest in diesen
Aspekten unterscheidet.

Der ’Notification Icon’ befindet sich in der Toolbar im
oberen Bereich des Systems.

#### Figure 4: Toolbar mit Benachrichtigungshinweis

#### Figure 3: Hinweis zur Umbennung einer Spalte

## 3.4 Die Toolbar

Um den Lernenden weitere Funktionen zur effizienten Be-
arbeitung der Aufgabe und Hilfestellungen aufzeigen zu k¨on-
nen, befindet sich am oberen Rand des Systems eine Tool-
bar (siehe Abbildung 4). Diese stellt aktuelle Informationen,
Hinweise und Hilfestellungen zur Verfugung. Wie bereits er- ¨
w¨ahnt gibt es hier die Auflistung der Hinweise zur Bearbei-
tung der aktuellen Aufgabe.

#### Figure 5: Toolbar mit ge¨offneten Benachrichtigungen

## 3.5 Feedback durch die Lernenden

Damit die Kommunikation und Interaktion der Lernenden
sich nicht nur auf das System und dessen Hinweise bezieht,
gibt es die Schaltfl¨ache ’Question and Feedback’. Hier k¨on-
nen die Lernenden Kontakt zu den Lehrk¨orpern aufnehmen.
Hierbei wird zwischen aufgabenpezifischen Fragen und Feed-
back unterschieden. Vor allem das Feedback ist gewunscht, ¨

Sind neue Benachrichtigungen eingetroffen, wird an dem
Icon einer Glocke ein roter Kreis angezeigt (siehe Abbil-
dung 4 und Abbildung 5). Neben den Hinweisen zur Bear-
beitung werden unter der Glocke zudem noch Hinweise auf
neue Empfehlungen gegeben. Gibt es zur aktuellen Aufgabe

### 3.6.3 Hilfetexte

da dieses dazu dient, das System an die Bedurfnisse der Ler- ¨
nenden anzupassen und eine kontinuierliche Verbesserung
voranzutreiben (siehe Abbildung 6).

Das System ist auch darauf ausgelegt, dass die Lernen-
den gegebenenfalls nicht die M¨oglichkeit haben Audio- oder
Videoinhalte abzurufen. Hier sind die Hilfetexte nutzlich. ¨
Die Hilfetexte sind Beschreibungen von Herausforderungen,
Fragestellungen, Datenbankthematiken oder Beispiele von
SQL-Code.

### 3.6.4 Hilfegrafiken

Hilfegrafiken stellen nicht nur Datenmodelle dar, sondern
um Zeichnungen oder Comics, die sich mit wenig Worten
einer Datenbankthematik annehmen.

### 3.6.5 Vordefinierte Hilfestellungen

Die Lernenden bekommen, basierend auf der Analyse des
Systems, zu der aktuellen Situation und zur Aufgabe Hilfe-
stellungen empfohlen. Diese k¨onnen sich dynamisch anpas-
sen und mussen nicht permanent verf ¨ ugbar bleiben. Emp- ¨
fehlungen k¨onnen entfernt werden, wenn bspw. Lernende die
Aufgabe wechseln oder sich der Fokus der Thematik ¨andert.
Vordefinierte Inhalte beziehen sich nicht zwingend auf eine

Aufgabe im Einzelnen. Sie k¨onnen Informationen betreffen,
die wichtig sind um ein Grundverst¨andnis fur die Kursin- ¨
halte zu erlangen. Auch wenn keine Challenges aktiv sind,
k¨onnen Inhalte bereit gestellt werden.

#### Figure 6: Feedbackfenster

Die Gesamtheit der multimedialen Inhalte wird nicht nur
im Rahmen der Aufgaben genutzt. Mit den Inhalten werden
Playlisten gefullt, die den Lernenden zur Verf ¨ ugung stehen ¨
um die Selbstlernphase zu unterstutzen. ¨

## 3.6 Mediale Hilfestellungen

Fur die Lernenden stehen verschiedene Arten von me- ¨
dialen Hilfestellungen zur Verfugung, die st ¨ ¨andig erg¨anzt,
produziert und weiterentwickelt werden. Dabei handelt es
sich um digitale Medien wie bspw. Screencasts, Erkl¨arvi-
deos, Podcasts, Hilfetexte und Hilfegrafiken. Diese Medien
werden kurz gehalten und sind thematisch nicht voneinan-
der abh¨angig, k¨onnen sich aber erg¨anzen und werden ggf. in
Gruppen mit oder ohne empfohlener Reihenfolge empfohlen.
Uber die Icons auf der linken Seite k ¨ ¨onnen aktuell be-
reitgestellte Medien abgerufen werden. Die Medien werden
in modalen Fenstern innerhalb der Anwendung aufgerufen.
Fur die Icons gibt es zwei Bereiche. Die grauen Icons bein- ¨
halten vordefinierte Hilfestellungen, wohingegen die grunen ¨
Icons aktuell empfohlene Hilfestellungen beinhalten.

### 3.6.6 Empfehlungen

Hilfestellungen und multimediale Elemente sollen zudem
zunehmend vom System empfohlen werden. ALEA nutzt
verschiedene Arten von Empfehlungsalgorithmen, die st¨an-
dig weiterentwickelt werden. Diese werden mit wachsender
Nutzung und Datenmenge ausgebaut und verbessert.

### 3.6.7 Metadaten

Ein wichtiger Aspekt fur die Zuweisung der medialen Hil- ¨
festellungen sind die hinterlegten Metadaten. Fur mediale ¨
Inhalte werden eine Reihe von Metadaten definiert, die es
den Empfehlungsalgorithmen erlauben, die Inhalte den Ler-
nenden zuzuordnen. Diese werden auch bei der Erstellung
von Aufgaben bzw. zur Zuordnung von Aufgaben im Rah-
men von Challenges zu Lernenden oder Gruppen von Ler-
nenden genutzt. Dies erm¨oglicht im Vorfeld die Zuordnung
der Hilfestellung zu Aufgaben. Ein direkt fur diese Aufgabe ¨
produzierter Podcast, soll in der Regel nicht als Hilfestellung
empfohlen werden.

### 3.6.1 Screencasts und Erklärvideos

Screencasts befassen sich mit der Anwendung und Nut-
zung von Software bzw. mit den Erkl¨arungen zu L¨osun-
gen dieser Aufgabentypen. Fur die Aufgaben zum ER-to- ¨
Relational-Mapping wurden bereits mehr als 50 Screencasts
produziert.

In kurzen aber pr¨agnanten Videos werden den Lernen-
den Inhalte aus dem Bereich vermittelt. Diese Screencasts
k¨onnen sich auf Aufgaben beziehen oder allgemeine Vorge-
hensweisen und Hinweise enthalten. Neben den Screencasts
finden die Lernenden hier zudem Erkl¨arvideos die allgemeine
Prinzipien von Datenbanken thematisieren.

## 3.7 Check and Submit

Um sich den zugeh¨origen SQL-Code anzeigen zu lassen
und zur Kontrolle der eigenen Eingaben, steht den Lernen-
den im unteren Bereich des Systems die Schaltfl¨ache ’Check
Input and Show SQL’ zur Verfugung. Zum Erzeugen des ¨
SQL-Codes wird die Check-Funktion durchlaufen. Diese baut
zwei Zeichenketten zusammen. Die erste Zeichenkette kann
direkt auf der Datenbank ausgefuhrt werden. Genutzt wird ¨
diese fur den Test, den die Lernenden w ¨ ¨ahrend der Bearbei-
tung machen k¨onnen und zudem fur die finale Abgabe der ¨
Aufgabe. Eine zweite Zeichenkette wird erzeugt und bein-
haltet HTML-Code. Dieser wird zur visuellen Darstellung
des SQL-Codes fur die Lernenden genutzt. ¨

### 3.6.2 Podcasts

Podcasts sollen, so wie die Screencasts, kompakt Informa-
tionen vermitteln. Die Themen k¨onnen hier sowohl Aufgaben-
oder Challenge-bezogen als auch allgemeingultig sein. Die ¨
Podcasts sind Dialoge zwischen zwei oder mehreren Spre-
chenden, die ein Thema diskutieren, um den Lernenden neue
Anreize zu bieten uber das Geh ¨ ¨orte nachzudenken. Auch
Hilfetexte k¨onnten vorgelesen werden.

de’ kopiert den angezeigten SQL-Code in die Zwischenablage
und ’Save to Script’ bietet die M¨oglichkeit den Code als Da-
tei lokal zu speichern. Damit der bereitgestellte SQL-Code
von den Lernenden auf unterschiedlichen Datenbanksyste-
men genutzt werden kann, k¨onnen diese den entsprechenden
Datentyp ausw¨ahlen.

Die Lernenden haben die M¨oglichkeit mit der Schaltfl¨a-
che ’Test on Database’ den ihren Eingaben entsprechen-
den DDL-Code direkt auf dem angebundenen Datenbank-
system zu testen. Die Ruckmeldung wird in dem Check- ¨

Input-Ausgabefenster ausgegeben. Hierbei wird einerseits ge-
testet, ob die Eingaben der Lernenden einen gultigen SQL- ¨
Code entsprechen. Andererseits wird die L¨osung unter Ver-
wendung der zur Aufgabe hinterlegten Informationen wei-
testgehend durch das System ausgewertet. Korrekte L¨osun-
gen von Aufgaben k¨onnen u. a. eine vorgegebene Anzahl von
Tabellen, Spalten, Constraints (Primary Keys, Uniques, Not
Nulls außerhalb von Primary Keys, Foreign Keys) und dar-
in enthaltene Attributanzahl bzw. eine jeweilige Mindest-
und Maximalanzahl erfordern, so dass L¨osungen als falsch
erkannt werden k¨onnen.

Die Auswertung der Aufgabe bzgl. der Sinnhaftigkeit der
Bezeichnungen bspw. von Tabellen oder Spalten, kann und
wird dabei nicht gepruft. Jedoch kann ¨ uber das Datenbank- ¨
system eine weitergehende Prufung abh ¨ ¨angig von vorliegen-
den Daten zur Aufgabe durchgefuhrt werden. ¨

Die Ausgabe einer Zwischenauswertung ohne wiederholte
Serveranfrage in der Toolbar ist m¨oglich, wenn die Infor-
mation zu gultigen L ¨ ¨osungsm¨oglichkeiten der Aufgabe be-
zogen auf die Anzahl der Elemente eindeutig ist und Varia-
tionen nur begrenzt m¨oglich sind. In der Datenbank k¨onnen
auch Angaben fur Aufgaben mit verschiedenartigen L ¨ ¨osun-
gen hinterlegt und ausgewertet werden. Insbesondere wenn
die Aufgabenstellungen komplexer werden, k¨onnen die Aus-
wertungen aufw¨andiger werden. Je nachdem wie die Lernen-
den ihre L¨osungen aufbauen kann sich bspw. die Anzahl der
Elemente in einem Constraint unterscheiden und trotzdem
eine richtige L¨osung erzeugen.

#### Figure 7: Challenge Auswahl und Hilfemedien

Die Ansicht des DDL-Codes soll den Lernenden einen an-
deren Blick auf die eigene L¨osung verschaffen (siehe Abbil-
dung 8). Damit soll der Bezug zwischen der Planung des Re-
lationenmodells und dem Verst¨andnis der Syntax der DDL-
Befehle (Data Definition Language) gest¨arkt werden.

#### Figure 8: Ausgabe des SQL-Codes und Ruckmeldung der Da- ¨ tenbank

Da die Datentypen fur die L ¨ ¨osung der Aufgabe nicht re-
levant sind, wird auf dem Datentyp ’variable character’ ab-
gebildet, der dem Datenbanksystem entspricht auf dem der
Code ausgefuhrt wird. Um den Lernenden die M ¨ ¨oglichkeit
zu bieten den entstandenen DDL-Code zu nutzen, gibt es die
Schaltfl¨achen ’Copy Code’ und ’Save to Script’. ’Copy Co-

Die Schaltfl¨ache ’Submit’ fuhrt die Lernenden zur Abgabe ¨
ihrer L¨osung. Zur Sicherheit und um Fehlklicks abzufangen
¨offnet sich, nachdem die Lernenden auf ’Submit’ gedruckt ¨
haben, ein weiteres Fenster. In diesem erhalten die Lernen-
den die Information, ob ihre L¨osung eine gultige L ¨ ¨osung sein

## 4.1 Erweiterte Tabellenansicht

k¨onnte. Ist dies der Fall, besteht die M¨oglichkeit die Aufgabe
abzugeben.

Fur die Bearbeitung der Aufgaben zur Normalisierung ¨
wurden die Bereiche zur Definition der Tabellen durch Funk-
tionen erg¨anzt (siehe Abbildung 10). Neben den bekannten
Funktionen der Benennung, L¨oschung und Hinzufugen von ¨
Spalten und Constraints, gibt es eine Schaltfl¨ache zur De-
aktivierung der Tabelle. Sobald eine Tabelle zerlegt werden
soll, muss sie deaktiviert werden. Sie wird nicht entfernt,
damit der Verlauf nachvollziehbar bleibt. Die durch die Zer-
legung neu entstehenden Tabellen mussen eingeben werden. ¨
Dabei soll uber ein Dropdown-Men ¨ u, welches alle inaktiven ¨
Tabellen auflistet, angegeben werden, aus welcher Tabelle
eine Tabelle jeweils entstanden ist.

In Lernphasen k¨onnen die Lernenden unfertige Aufgaben
zur sp¨ateren Bearbeitung uberspringen. Anstatt einer m ¨ ¨og-
lichen Ja/Nein-Abfrage, ob die Aufgabe abgegeben werden
soll, kann zwischen ’Zuruck zur Bearbeitung’ oder ’ ¨ Uber- ¨
springen’ (siehe Abbildung 9) gew¨ahlt werden. Diese un-
fertigen Aufgaben werden nicht aus dem System entfernt.
Aufgaben die als Lern- oder Testataufgaben gelten mussen ¨
solange wiederholt werden, bis die Eingabe gultig ist. In der ¨
Abbildung 7 ist zu sehen, dass eine Challenge Aufgaben zur
Auswahl der Bearbeitungsreihenfolge beinhalten kann. Ei-
ne Challenge bleibt bestehen bis alle Aufgaben erfolgreich
bearbeitet wurden.

#### Figure 10: Tabellendefinition mit erweiterten Funktionen

#### Figure 11: Tabellendefinition finalisieren

Die Studierenden sollen fur jede neu entstandene Tabelle ¨
die Normalform angeben. Dazu befindet sich ein Auswahl-
feld im Kopfbereich der Tabellendefinition. Die Lernenden
sollen zudem jeweils zu jeder Zerlegung angeben, aus wel-
chen Grunden diese durchgef ¨ uhrt werden musste. Dazu be- ¨
findet sich ein Textfeld im Fußbereich der Tabellendefinition.
Zudem ist es erwunscht hier weitere Anmerkungen, Fragen, ¨
Notizen und Feedback der Lernenden zu erhalten. Sobald
fur eine Tabelle die geforderte Normalform erreicht wurde, ¨
soll die Tabelle finalisiert werden (siehe Abbildung 11).

#### Figure 9: Abgabe einer Lernaufgabe

## 3.8 Prüfungsmodus

Das System ist zum einen fur die Lernphase und zum ¨
anderen fur die Pr ¨ ufungsphase gedacht. Hierf ¨ ur sieht das ¨
System vor, dass Funktionen, welche fur Lernphasen wich- ¨
tig sind, fur die Pr ¨ ufungen deaktiviert werden. Die Hilfe- ¨
stellungen, die sich auf Informationen zu gultigen L ¨ ¨osungen
beziehen, sind nicht verfugbar. Empfehlungen und alle da- ¨
mit verbundenen Hilfsmedien sind ebenfalls nicht erreich-
bar. In dem Fenster ’Check Input und Show SQL’ werden
die Schaltfl¨achen auf ’Close’ und ’Submit’ reduziert. Eine
zweistufige Abfrage nach dem ’Submit’ bleibt zwar beste-
hen, jedoch wird das erscheinende Fenster auf eine erneute
Frage, ob die L¨osung abgegeben werden soll, reduziert.

## 4.2 Erweiterte Ansichten

Die Komponente fur die Aufgaben zur Normalisierung ¨
wird durch eine weitere ’Quick View’ erg¨anzt. Auf der rech-
ten Seite finden die Lernenden eine Ubersicht ¨ uber die aktu- ¨
ell aktiven und inaktiven Tabellen. Neben dem Tabellenna-
men sind hier auch die Spaltennamen gelistet. Ebenso k¨on-
nen die Begrundungen angezeigt werden. ¨

5. ZUSAMMENFASSUNG UND AUSBLICK
Komponenten zur Bearbeitung von Aufgaben zum ER-
to-Relational-Mapping und zur Normalisierung werden dar-
gestellt. Vielf¨altige Interaktionen und Hilfestellungen bspw.
Empfehlungen von multimedialen digitalen Elementen wer-
den zur Verbesserung des Lernprozesses integriert. Durch
verst¨arkte Nutzung der Komponenten und dem Anwachsen
der Daten k¨onnen Empfehlungen und Learning Analytics
weiter verbessert werden.

## 4. AUFGABENTYP NORMALISIERUNG

Ein weiterer Aufgabentyp des ALEA-Systems ist die Nor-
malisierung. Dieser Aufgabentyp nutzt die Grundfunktionen
der Mapping-Aufgaben, da Tabellen und Constraints defi-
niert werden mussen. ¨

In einer Aufgabenstellung zur Normalisierung erhalten die
Lernenden eine oder mehrere Tabellen sowie eine Aquiva- ¨
lenzmenge zu der Menge aller fur die Tabellen g ¨ ultigen Funk- ¨
tionalen Abh¨angigkeiten. Die Normalform der Tabellen ist
anzugeben. Die Tabellen sind unter Verwendung des Zerle-
gungsverfahrens in der Regel in 3NF zu uberf ¨ uhren, sofern ¨
sie sich nicht in der dritten Normalform befinden. Die Ta-
bellen k¨onnen in der Aufgabenstellung zur Verdeutlichung
mit Daten gefullt sein. Zur besseren ¨ Ubersicht lassen sich ¨
die Inhalte der Tabellen bei Bedarf aus- und einblenden.
Die Darstellung der funktionalen Abh¨angigkeiten l¨asst sich,
wie auch beim ALEA-Mapping das vorgegebene Datenmo-
dell, durch einen Klick in ein bewegliches, modales Fenster
umwandeln oder in einen neuen Tab.

## Literatur

[1] D. Becher. DB-Normalizer. TU Munchen, 2021. ¨ https:
//db.in.tum.de/teaching/ws2021/grundlagen/.

[2] P. Chen. The-Entity-Relationship-Model. ACM transac-
tions on database systems (TODS), 1976.

[3] H. Faeskorn-Woyke and B. Bertelsmeier. EDB - Das
eLearning Datenbank Portal der TH K¨oln., 2021.

[4] K. Schneider and F. Keller. Das Daten Caf´e an der Hoch-
schule Harz, 2021. http://datencafe.hs-harz.de/.
