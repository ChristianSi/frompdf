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
len. Die typischerweise in einführenden Datenbanklehrver-
anstaltungen enthaltenen Aufgaben in den Bereichen ER-
to-Relational-Mapping und Normalisierung sind in der Re-
gel sehr aufwendig zu korrigieren. Für die Lernenden ist ein
Üben dieser Aufgaben jedoch sehr hilfreich. Für das ALEA-
System wurden daher interaktive Komponenten für die bei-
den Bereiche entwickelt und genutzt.

E-Learning-Systeme finden immer weitere Verbreitung in
den verschiedensten Lehrbereichen. Auch im Bereich Da-
tenbanken gibt es eine Vielzahl von Anwendungsgebieten.
Es werden zwei Komponenten vorgestellt, die bei der Leh-
re im Rahmen von Aufgaben bezogen auf ER-to-Relational-
Mapping und Normalisierung unterstützen sollen. Vielfältige
Interaktionen und Hilfestellungen bspw. Empfehlungen von
multimedialen digitalen Elementen werden zur Verbesserung
des Lernprozesses integriert.

## Keywords

Diese Komponenten und deren vielfältige Interaktions-
möglichkeiten werden im Folgenden thematisiert. Grund-

E-Learning-Systeme, ER-to-Relational-Mapping, SQL-DDL,
Normalisierung, Recommender-Systeme

sätzliche Möglichkeiten zur Interaktion des E-Learning-Systems
werden hierbei veranschaulicht.

Nach einer kurzen Einführung in die grundlegenden Aspek-
te des Systems wird auf die Mapping-Aufgaben aus dem
Bereich ER-to-Relational-Mapping eingegangen. Die vielfäl-
tigen Arten der Interaktionen bei der Bearbeitung werden
erläutert. Die Bearbeitung der Normalisierungsaufgaben er-
fordert ergänzende Interaktionsmöglichkeiten und Ansich-
ten, die im folgenden Kapitel beschrieben werden. Schließ-
lich werden die Ergebnisse zusammengefasst und ein Aus-
blick gegeben.

## 1. EINLEITUNG

Der Einsatz von E-Learning-Systemen wird zunehmend
bedeutsamer. Durch Erweiterungen der Interaktions- und

Feedbackmöglichkeiten kann die Nützlichkeit der E-Learning-
Systeme verbessert werden und den Lernenden nicht nur
in Selbstlernphasen Hilfestellungen und Unterstützungsmög-
lichkeiten im Lernprozess zur Verfügung stellen. Im Kon-
text von Leistungsermittlungen können Hilfestellungen ein-
geschränkt werden, trotzdem sollen die Korrektur- und Ab-
fragemöglichkeiten erleichtert und verbessert sein.

## 2. GRUNDLEGENDE ASPEKTE

Das Konzept ER-to-Relational-Mapping und die Norma-
lisierung eines Relationenmodells bzw. relationalen Daten-

Das ALEA-System ist ein datenbankbasiertes E-Learning-
System für Datenbanken und besteht aus verschiedenen Kom-
ponenten für unterschiedliche Bereiche.

modells sind zwei grundsätzliche Gebiete, die in einführen-
den Lehrveranstaltung im Bereich Datenbanken behandelt
werden. In den letzten Jahren wurden verstärkt E-Learning-
Syteme eingesetzt, sodass auch diese Gebiete von diesen Sys-
temen unterstützt werden sollten. Das E-Learning Daten-
bank Portal edb-Portal der TH Köln [3] ist ein umfangrei-
ches E-Learning-Angebot für den Bereich Datenbanken und
enthält auch einen ER-Trainer. An der TU München gibt es
den DB-Normalizer [1].

Das System wurde hauptsächlich mit Java und JavaS-
cript entwickelt. Als Entwurfsmuster wurde MVC2 verwen-
det, das heißt, es gibt eine logische Trennung zwischen Logik
und Anzeige. Die Anzeige basiert auf HTML5 in Kombina-
tion mit CSS und wurde mit JavaScript erweitert, um die
Interaktionsmöglichkeiten zu erhöhen und verbessern. Mit-
hilfe von AJAX werden nach Bedarf Daten an den Server
gesendet ohne dass die Webseite neu geladen wird. Zur Ver-
waltung der Information über Aufgaben, Lösungen, Lernen-
de usw. werden Datenbanksysteme eingebunden.

## 3. AUFGABENTYP ER-TO-RELATIONAL- MAPPING

32nd GI-Workshop on Foundations of Databases (Grundlagen von Daten-
banken), September 01-03, 2021, Munich, Germany.
Copyright © 2021 for this paper by its authors. Use permitted under Crea-
tive Commons License Attribution 4.0 International (CC BY 4.0).

Für die Thematik des ER-to-Relational-Mapping ist ein
Fragentyp vorgesehen, der das Thema der Erstellung von
relationalen Datenmodellen beinhaltet auf Basis vorgegebe-

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
der notwendigen Tabellen. In diesen können durch Schalt-
flächen Tabellenbezeichnung, Spalten und Constraints hin-
zugefügt werden.

lisiert werden. Diese beziehen sich auf grundsätzliche Struk-
turen und Regeln bei den Tabellendefinitionen. Weiterhin
kann der äquivalente DDL-Code aus den entstandenen Re-
lationen erzeugt werden, um eine Prüfung auf dem Daten-
bankserver auszuführen. Darüber hinaus können durch die
in der Datenbank zu der Aufgabe hinterlegten Informatio-
nen weitere Prüfungen durchgeführt werden, die sich dar-
über hinaus speziell auf die Aufgabe und deren Anforde-
rungen beziehen. Die Korrektheit einer Lösung kann zwar
generell nicht automatisch entschieden werden, aber Fehler
können weitestgehend erkannt werden. Die Gestaltung der
Aufgaben kann dies erleichtern.

## 3.1 Bearbeitung der Aufgaben

Zur Lösung der Mapping-Aufgaben gibt es für jede Akti-
on eine entsprechende Schaltfläche. Das System erlaubt es
den Lernenden nicht mehrere Aktionen parallel auszuführen.
Erst nachdem eine Aktion abgeschlossen ist, kann eine neue
gestartet werden. Für diesen Zweck werden alle anderen Ak-
tionen durch das Deaktivieren der entsprechenden Buttons
unterbunden (siehe Abbildung 1). Wird zum Beispiel eine
neue Tabelle definiert, so muss für die Tabelle ein Name
eingegeben werden, bevor Spalten hinzugefügt werden kön-
nen. Wiederum muss mindestens eine Spalte zu einer Tabel-
le gehören damit Constraints erzeugt werden können (siehe
Abbildung 2).

Bereits bei der Eingabe sind ausgewählte Strukturen und
Regeln bezogen auf die Tabellen und Constraints einzuhal-
ten, sodass diese idealerweise von den Studierenden verin-
nerlicht werden.

Der Composer fungiert grundlegend als dynamisch erweiter-
bares HTML-Formular. Die durch die Lernenden ausgelös-
ten Aktionen durchlaufen in dieser Phase nicht jedes Mal
eine Validierungsroutine auf dem Server, wodurch Ressour-
cen gespart werden.

Das konzeptuelle Datenmodell ist in den Aufgabenstellun-
gen als Bild enthalten. Dieses kann im oberen Bereich des
Systems eingeblendet werden. Damit die Lernenden zu je-
der Zeit einen freien Blick auf das abzubildende ER-Modell
haben, lässt sich dieses durch einen Klick in einem frei be-
weglichen modalen Fenster oder einem neuen Tab öffnen.
So besteht die Möglichkeit auch bei größeren Datenmodel-
len, bei deren Verarbeitung vermehrt gescrollt werden muss,
den Überblick zu behalten. Zudem kann die Größe des ab-
gekoppelten Fensters durch Ziehen mit der Maus verändert
werden.

Nicht alle logischen Zusammenhänge müssen durch das
eingebundene Datenbanksystem geprüft werden. Ein Bei-
spiel für diese Art der Prüfung ist die Löschung von Spal-
ten. Durch eine Routine innerhalb der JavaScript-Skripte
wird geprüft, ob die Spalte für Constraints der aktuellen
oder anderer Tabellen genutzt wird. Ist dies der Fall, gibt
das System eine Meldung aus und der Löschvorgang wird
abgebrochen. Die Umbenennung einer Spalte wird ebenfalls
durch eine JavaScript-Routine geprüft. Dieser Vorgang wird
jedoch innerhalb der aktuellen Tabelle zugelassen und ein
Hinweis ausgegeben der darauf hinweist, dass andere Ta-
bellen mit dieser Spalte in Zusammenhang stehen könnten,
sodass eine manuelle Prüfung notwendig ist. Die durch die
Änderung des Spaltennamens notwendigen Anpassungen in-
nerhalb der Tabellendefinition werden automatisch durchge-
führt. Da diese Änderungen die Lernenden von relevanteren
Aspekten ablenken würden.

Das Zulassen von Aktionen trotz Inkonsistenz kann sinn-
voll sein. Ein Beispiel ist ein Fremdschlüssel-Constraint, wel-
cher angelegt wird bevor die referenzierten Spalten als Kan-
didatenschlüssel (Primary Key oder NOT NULL/Unique
Constraints) definiert wurden. Ansonsten würden positive
Aktionen zu stark von erzwungenen Reihenfolgeabhängig-
keiten gestört werden. Die Lernenden können jederzeit den
dem aktuellen Zustand entsprechenden DDL-Code über das
Datenbanksystem prüfen lassen. Für Leistungsbewertungen
kann diese Möglichkeit eingeschränkt werden.

#### Figure 1: Aktive Bearbeitung einer Spalte

## 3.2 Prüfen der Eingaben

## 3.3 Reaktionen des Systems auf Eingaben

Ein wichtiger Aspekt der Mapping-Aufgaben ist es die
Eingaben der Lernenden so früh und umfangreich wie sinn-
voll und möglich zu prüfen. Bereits bei den Eingaben werden
clientseitige Abfragen genutzt, welche durch JavaScript rea-

Jede Aktion ruft eine Reaktion hervor. Wenn die Lernen-
den als Beispiel eine Spalte umbenennen, werden die Fol-
gen dieser Aktion in einer Meldung visuell dargestellt, da

ggfs. Anpassungen aufgrund von Abhängigkeiten in anderen
Tabellen durch die Lernenden notwendig werden können.
Hierbei wird angestrebt, dass diese Meldungen motivierend
und angepasst an die Sprache der Lernenden formuliert wer-
den. Die Meldungstexte können im System angepasst wer-
den. Hier bieten sich weitere Möglichkeiten für intelligente
Empfehlungsfunktionen. Die Lernenden dürfen und sollen
Fehler machen aus denen sie lernen können. Das Wissen soll
sich durch Wiederholen verfestigen.

weiterführende Informationen, so können diese in verschie-
denen medialen Formen, z.B. Screencasts, Podcasts, Hilfe-
texte, Hilfegrafiken, vorliegen und abgerufen werden.

Die Farbe der Icons kann, wie auch die Ansprache oder
empfohlene Medien, durch die Empfehlungsalgorithmen an-
gepasst werden.

Neben diesen Hinweisen werden zudem noch Informatio-
nen zum aktuellen Bearbeitungsstand der Aufgabe gegeben.
Diese Informationen finden die Lernenden unter dem Info-
Icon (siehe Abbildung 5).

Für die Mapping-Aufgaben sind diese Hinweise vorteil-
haft, um die Übersicht über den aktuellen Bearbeitungs-
stand zu erhalten. Die Hinweise zeigen mögliche Komplika-
tionen auf und sollen so das Verständnis der Lernenden für
logische Zusammenhänge innerhalb des Relationenmodells
erhöhen. Deswegen kann es hilfreich, dass in den Hinweisen
angezeigt wird, dass Änderungen in der aktuellen Tabelle
durchaus Auswirkungen auf die Constraints anderer Tabel-
len haben könnten. So sind die Lernenden angehalten diese
aktiv anzupassen.

Wenn bspw. die Lösung bzw. die gültigen Lösungen der
Aufgabe eine bestimmte Anzahl an Uniques erfordern oder
eine minimale oder maximale Anzahl an Uniques enthal-
ten dürfen, kann den Lernenden mitgeteilt werden, dass die
Anzahl der Uniques noch nicht einer gültigen Lösung ent-
spricht. Hierbei wird den Lernenden in der Regel keine kon-
krete Anzahl genannt, lediglich dass diese noch nicht gültig
ist.

Zudem können hier Hilfetexte erscheinen, die sich auf die
Arbeitsweise der Lernenden beziehen. Bemerkt das System
z.B. dass es im Bereich der Foreign Key Constraints zu
vermehrten Interaktionen kommt, können hier Definitionen
oder Tipps zum Thema Foreign Key Constraints angezeigt
werden. Dies ist abhängig von den eingesetzten hybriden
Filter- und Empfehlungsalgorithmen.

Die eben genannten Hinweise erscheinen als modale Fens-
ter mittig in der Browserausgabe, um die Aufmerksamkeit
der Lernenden einzufangen und die Wichtigkeit dieser Än-
derung in den Vordergrund zu stellen (siehe Abbildung 3).
Diese Hinweise sollen während der Bearbeitung der Aufga-
be weiterhin zur Verfügung stehen und werden deshalb als
zeitlich sortierte Liste abrufbar über ein ’Notification Icon’
bereitgestellt. Eine Aufteilung der Listen in unterschiedli-
che thematische Listen wird nach weiteren Evaluierungen
entschieden. Diejenigen Nachrichten, die seit dem letzten
Öffnen der Liste durch die Lernenden hinzugekommen sind,
werden farblich hervorgehoben.

Um den Lernenden eine sog. ’Quick View’ über den aktuel-
len Bearbeitungsstand zu geben, befinden sich in der Toolbar
kleine Icons, welche repräsentativ für Elemente der Model-
lierung stehen. Dies sind von links nach rechts die Gesamtan-
zahl der aktiven Tabellen, der aktiven Spalten, der Primary
Key Constraints, der Unique Constraints, der Foreign Key
Constraints und der NOT NULLs außerhalb von Primary
Key Constraints (siehe Abbildung 4). Durch die Übersicht
der aktuell aktiven Elemente sollen die Lernenden eine kom-
pakte Übersicht über den aktuellen Zustand erhalten. Insbe-
sondere in Übungsphasen, in denen die Mindestanzahl oder
die exakte Anzahl der benötigten Elemente vorgegeben sein
kann, ist diese Ansicht hilfreich um zu eruieren, wie weit
sich das eigene Ergebnis vom gesuchten zumindest in diesen
Aspekten unterscheidet.

Der ’Notification Icon’ befindet sich in der Toolbar im
oberen Bereich des Systems.

#### Figure 4: Toolbar mit Benachrichtigungshinweis

#### Figure 3: Hinweis zur Umbennung einer Spalte

## 3.4 Die Toolbar

Um den Lernenden weitere Funktionen zur effizienten Be-
arbeitung der Aufgabe und Hilfestellungen aufzeigen zu kön-
nen, befindet sich am oberen Rand des Systems eine Tool-
bar (siehe Abbildung 4). Diese stellt aktuelle Informationen,
Hinweise und Hilfestellungen zur Verfügung. Wie bereits er-
wähnt gibt es hier die Auflistung der Hinweise zur Bearbei-
tung der aktuellen Aufgabe.

#### Figure 5: Toolbar mit geöffneten Benachrichtigungen

## 3.5 Feedback durch die Lernenden

Damit die Kommunikation und Interaktion der Lernenden
sich nicht nur auf das System und dessen Hinweise bezieht,
gibt es die Schaltfläche ’Question and Feedback’. Hier kön-
nen die Lernenden Kontakt zu den Lehrkörpern aufnehmen.
Hierbei wird zwischen aufgabenpezifischen Fragen und Feed-
back unterschieden. Vor allem das Feedback ist gewünscht,

Sind neue Benachrichtigungen eingetroffen, wird an dem
Icon einer Glocke ein roter Kreis angezeigt (siehe Abbil-
dung 4 und Abbildung 5). Neben den Hinweisen zur Bear-

beitung werden unter der Glocke zudem noch Hinweise auf
neue Empfehlungen gegeben. Gibt es zur aktuellen Aufgabe

### 3.6.3 Hilfetexte

da dieses dazu dient, das System an die Bedürfnisse der Ler-
nenden anzupassen und eine kontinuierliche Verbesserung
voranzutreiben (siehe Abbildung 6).

Das System ist auch darauf ausgelegt, dass die Lernen-
den gegebenenfalls nicht die Möglichkeit haben Audio- oder
Videoinhalte abzurufen. Hier sind die Hilfetexte nützlich.
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
stellungen empfohlen. Diese können sich dynamisch anpas-
sen und müssen nicht permanent verfügbar bleiben. Emp-
fehlungen können entfernt werden, wenn bspw. Lernende die
Aufgabe wechseln oder sich der Fokus der Thematik ändert.
Vordefinierte Inhalte beziehen sich nicht zwingend auf eine

Aufgabe im Einzelnen. Sie können Informationen betreffen,
die wichtig sind um ein Grundverständnis für die Kursin-
halte zu erlangen. Auch wenn keine Challenges aktiv sind,
können Inhalte bereit gestellt werden.

#### Figure 6: Feedbackfenster

Die Gesamtheit der multimedialen Inhalte wird nicht nur
im Rahmen der Aufgaben genutzt. Mit den Inhalten werden
Playlisten gefüllt, die den Lernenden zur Verfügung stehen
um die Selbstlernphase zu unterstützen.

## 3.6 Mediale Hilfestellungen

Für die Lernenden stehen verschiedene Arten von me-
dialen Hilfestellungen zur Verfügung, die ständig ergänzt,
produziert und weiterentwickelt werden. Dabei handelt es
sich um digitale Medien wie bspw. Screencasts, Erklärvi-
deos, Podcasts, Hilfetexte und Hilfegrafiken. Diese Medien
werden kurz gehalten und sind thematisch nicht voneinan-
der abhängig, können sich aber ergänzen und werden ggf. in
Gruppen mit oder ohne empfohlener Reihenfolge empfohlen.

### 3.6.6 Empfehlungen

Hilfestellungen und multimediale Elemente sollen zudem
zunehmend vom System empfohlen werden. ALEA nutzt
verschiedene Arten von Empfehlungsalgorithmen, die stän-
dig weiterentwickelt werden. Diese werden mit wachsender
Nutzung und Datenmenge ausgebaut und verbessert.

Über die Icons auf der linken Seite können aktuell be-
reitgestellte Medien abgerufen werden. Die Medien werden
in modalen Fenstern innerhalb der Anwendung aufgerufen.
Für die Icons gibt es zwei Bereiche. Die grauen Icons bein-
halten vordefinierte Hilfestellungen, wohingegen die grünen
Icons aktuell empfohlene Hilfestellungen beinhalten.

### 3.6.7 Metadaten

Ein wichtiger Aspekt für die Zuweisung der medialen Hil-
festellungen sind die hinterlegten Metadaten. Für mediale
Inhalte werden eine Reihe von Metadaten definiert, die es
den Empfehlungsalgorithmen erlauben, die Inhalte den Ler-
nenden zuzuordnen. Diese werden auch bei der Erstellung
von Aufgaben bzw. zur Zuordnung von Aufgaben im Rah-
men von Challenges zu Lernenden oder Gruppen von Ler-
nenden genutzt. Dies ermöglicht im Vorfeld die Zuordnung
der Hilfestellung zu Aufgaben. Ein direkt für diese Aufgabe
produzierter Podcast, soll in der Regel nicht als Hilfestellung
empfohlen werden.

### 3.6.1 Screencasts und Erklärvideos

Screencasts befassen sich mit der Anwendung und Nut-
zung von Software bzw. mit den Erklärungen zu Lösun-
gen dieser Aufgabentypen. Für die Aufgaben zum ER-to-
Relational-Mapping wurden bereits mehr als 50 Screencasts
produziert.

In kurzen aber prägnanten Videos werden den Lernen-
den Inhalte aus dem Bereich vermittelt. Diese Screencasts
können sich auf Aufgaben beziehen oder allgemeine Vorge-
hensweisen und Hinweise enthalten. Neben den Screencasts
finden die Lernenden hier zudem Erklärvideos die allgemeine
Prinzipien von Datenbanken thematisieren.

## 3.7 Check and Submit

Um sich den zugehörigen SQL-Code anzeigen zu lassen
und zur Kontrolle der eigenen Eingaben, steht den Lernen-
den im unteren Bereich des Systems die Schaltfläche ’Check
Input and Show SQL’ zur Verfügung. Zum Erzeugen des
SQL-Codes wird die Check-Funktion durchlaufen. Diese baut
zwei Zeichenketten zusammen. Die erste Zeichenkette kann
direkt auf der Datenbank ausgeführt werden. Genutzt wird
diese für den Test, den die Lernenden während der Bearbei-
tung machen können und zudem für die finale Abgabe der
Aufgabe. Eine zweite Zeichenkette wird erzeugt und bein-
haltet HTML-Code. Dieser wird zur visuellen Darstellung
des SQL-Codes für die Lernenden genutzt.

### 3.6.2 Podcasts

Podcasts sollen, so wie die Screencasts, kompakt Informa-
tionen vermitteln. Die Themen können hier sowohl Aufgaben-
oder Challenge-bezogen als auch allgemeingültig sein. Die
Podcasts sind Dialoge zwischen zwei oder mehreren Spre-
chenden, die ein Thema diskutieren, um den Lernenden neue
Anreize zu bieten über das Gehörte nachzudenken. Auch
Hilfetexte könnten vorgelesen werden.

de’ kopiert den angezeigten SQL-Code in die Zwischenablage
und ’Save to Script’ bietet die Möglichkeit den Code als Da-
tei lokal zu speichern. Damit der bereitgestellte SQL-Code
von den Lernenden auf unterschiedlichen Datenbanksyste-
men genutzt werden kann, können diese den entsprechenden
Datentyp auswählen.

Die Lernenden haben die Möglichkeit mit der Schaltflä-
che ’Test on Database’ den ihren Eingaben entsprechen-
den DDL-Code direkt auf dem angebundenen Datenbank-
system zu testen. Die Rückmeldung wird in dem Check-

Input-Ausgabefenster ausgegeben. Hierbei wird einerseits ge-
testet, ob die Eingaben der Lernenden einen gültigen SQL-
Code entsprechen. Andererseits wird die Lösung unter Ver-
wendung der zur Aufgabe hinterlegten Informationen wei-
testgehend durch das System ausgewertet. Korrekte Lösun-
gen von Aufgaben können u. a. eine vorgegebene Anzahl von
Tabellen, Spalten, Constraints (Primary Keys, Uniques, Not
Nulls außerhalb von Primary Keys, Foreign Keys) und dar-
in enthaltene Attributanzahl bzw. eine jeweilige Mindest-
und Maximalanzahl erfordern, so dass Lösungen als falsch
erkannt werden können.

Die Auswertung der Aufgabe bzgl. der Sinnhaftigkeit der
Bezeichnungen bspw. von Tabellen oder Spalten, kann und
wird dabei nicht geprüft. Jedoch kann über das Datenbank-
system eine weitergehende Prüfung abhängig von vorliegen-
den Daten zur Aufgabe durchgeführt werden.

Die Ausgabe einer Zwischenauswertung ohne wiederholte
Serveranfrage in der Toolbar ist möglich, wenn die Infor-
mation zu gültigen Lösungsmöglichkeiten der Aufgabe be-
zogen auf die Anzahl der Elemente eindeutig ist und Varia-
tionen nur begrenzt möglich sind. In der Datenbank können
auch Angaben für Aufgaben mit verschiedenartigen Lösun-
gen hinterlegt und ausgewertet werden. Insbesondere wenn
die Aufgabenstellungen komplexer werden, können die Aus-
wertungen aufwändiger werden. Je nachdem wie die Lernen-
den ihre Lösungen aufbauen kann sich bspw. die Anzahl der
Elemente in einem Constraint unterscheiden und trotzdem
eine richtige Lösung erzeugen.

#### Figure 7: Challenge Auswahl und Hilfemedien

Die Ansicht des DDL-Codes soll den Lernenden einen an-
deren Blick auf die eigene Lösung verschaffen (siehe Abbil-
dung 8). Damit soll der Bezug zwischen der Planung des Re-
lationenmodells und dem Verständnis der Syntax der DDL-
Befehle (Data Definition Language) gestärkt werden.

#### Figure 8: Ausgabe des SQL-Codes und Rückmeldung der Da- tenbank

Da die Datentypen für die Lösung der Aufgabe nicht re-
levant sind, wird auf dem Datentyp ’variable character’ ab-
gebildet, der dem Datenbanksystem entspricht auf dem der
Code ausgeführt wird. Um den Lernenden die Möglichkeit
zu bieten den entstandenen DDL-Code zu nutzen, gibt es die
Schaltflächen ’Copy Code’ und ’Save to Script’. ’Copy Co-

Die Schaltfläche ’Submit’ führt die Lernenden zur Abgabe
ihrer Lösung. Zur Sicherheit und um Fehlklicks abzufangen
öffnet sich, nachdem die Lernenden auf ’Submit’ gedrückt
haben, ein weiteres Fenster. In diesem erhalten die Lernen-
den die Information, ob ihre Lösung eine gültige Lösung sein

## 4.1 Erweiterte Tabellenansicht

könnte. Ist dies der Fall, besteht die Möglichkeit die Aufgabe
abzugeben.

Für die Bearbeitung der Aufgaben zur Normalisierung
wurden die Bereiche zur Definition der Tabellen durch Funk-
tionen ergänzt (siehe Abbildung 10). Neben den bekannten
Funktionen der Benennung, Löschung und Hinzufügen von
Spalten und Constraints, gibt es eine Schaltfläche zur De-
aktivierung der Tabelle. Sobald eine Tabelle zerlegt werden
soll, muss sie deaktiviert werden. Sie wird nicht entfernt,
damit der Verlauf nachvollziehbar bleibt. Die durch die Zer-
legung neu entstehenden Tabellen müssen eingeben werden.
Dabei soll über ein Dropdown-Menü, welches alle inaktiven
Tabellen auflistet, angegeben werden, aus welcher Tabelle
eine Tabelle jeweils entstanden ist.

In Lernphasen können die Lernenden unfertige Aufgaben
zur späteren Bearbeitung überspringen. Anstatt einer mög-
lichen Ja/Nein-Abfrage, ob die Aufgabe abgegeben werden
soll, kann zwischen ’Zurück zur Bearbeitung’ oder ’ Über-
springen’ (siehe Abbildung 9) gewählt werden. Diese un-
fertigen Aufgaben werden nicht aus dem System entfernt.
Aufgaben die als Lern- oder Testataufgaben gelten müssen
solange wiederholt werden, bis die Eingabe gültig ist. In der
Abbildung 7 ist zu sehen, dass eine Challenge Aufgaben zur
Auswahl der Bearbeitungsreihenfolge beinhalten kann. Ei-
ne Challenge bleibt bestehen bis alle Aufgaben erfolgreich
bearbeitet wurden.

#### Figure 10: Tabellendefinition mit erweiterten Funktionen

#### Figure 11: Tabellendefinition finalisieren

Die Studierenden sollen für jede neu entstandene Tabelle
die Normalform angeben. Dazu befindet sich ein Auswahl-
feld im Kopfbereich der Tabellendefinition. Die Lernenden
sollen zudem jeweils zu jeder Zerlegung angeben, aus wel-
chen Gründen diese durchgeführt werden musste. Dazu be-
findet sich ein Textfeld im Fußbereich der Tabellendefinition.
Zudem ist es erwünscht hier weitere Anmerkungen, Fragen,
Notizen und Feedback der Lernenden zu erhalten. Sobald
für eine Tabelle die geforderte Normalform erreicht wurde,
soll die Tabelle finalisiert werden (siehe Abbildung 11).

#### Figure 9: Abgabe einer Lernaufgabe

## 3.8 Prüfungsmodus

Das System ist zum einen für die Lernphase und zum
anderen für die Prüfungsphase gedacht. Hierfür sieht das
System vor, dass Funktionen, welche für Lernphasen wich-
tig sind, für die Prüfungen deaktiviert werden. Die Hilfe-
stellungen, die sich auf Informationen zu gültigen Lösungen
beziehen, sind nicht verfügbar. Empfehlungen und alle da-
mit verbundenen Hilfsmedien sind ebenfalls nicht erreich-
bar. In dem Fenster ’Check Input und Show SQL’ werden
die Schaltflächen auf ’Close’ und ’Submit’ reduziert. Eine
zweistufige Abfrage nach dem ’Submit’ bleibt zwar beste-
hen, jedoch wird das erscheinende Fenster auf eine erneute
Frage, ob die Lösung abgegeben werden soll, reduziert.

## 4.2 Erweiterte Ansichten

Die Komponente für die Aufgaben zur Normalisierung
wird durch eine weitere ’Quick View’ ergänzt. Auf der rech-
ten Seite finden die Lernenden eine Übersicht über die aktu-
ell aktiven und inaktiven Tabellen. Neben dem Tabellenna-
men sind hier auch die Spaltennamen gelistet. Ebenso kön-
nen die Begründungen angezeigt werden.

5. ZUSAMMENFASSUNG UND AUSBLICK
Komponenten zur Bearbeitung von Aufgaben zum ER-
to-Relational-Mapping und zur Normalisierung werden dar-
gestellt. Vielfältige Interaktionen und Hilfestellungen bspw.
Empfehlungen von multimedialen digitalen Elementen wer-
den zur Verbesserung des Lernprozesses integriert. Durch
verstärkte Nutzung der Komponenten und dem Anwachsen
der Daten können Empfehlungen und Learning Analytics
weiter verbessert werden.

## 4. AUFGABENTYP NORMALISIERUNG

Ein weiterer Aufgabentyp des ALEA-Systems ist die Nor-
malisierung. Dieser Aufgabentyp nutzt die Grundfunktionen
der Mapping-Aufgaben, da Tabellen und Constraints defi-
niert werden müssen.

In einer Aufgabenstellung zur Normalisierung erhalten die
Lernenden eine oder mehrere Tabellen sowie eine Äquiva-
lenzmenge zu der Menge aller für die Tabellen gültigen Funk-
tionalen Abhängigkeiten. Die Normalform der Tabellen ist
anzugeben. Die Tabellen sind unter Verwendung des Zerle-
gungsverfahrens in der Regel in 3NF zu überführen, sofern
sie sich nicht in der dritten Normalform befinden. Die Ta-
bellen können in der Aufgabenstellung zur Verdeutlichung
mit Daten gefüllt sein. Zur besseren Übersicht lassen sich
die Inhalte der Tabellen bei Bedarf aus- und einblenden.
Die Darstellung der funktionalen Abhängigkeiten lässt sich,
wie auch beim ALEA-Mapping das vorgegebene Datenmo-
dell, durch einen Klick in ein bewegliches, modales Fenster
umwandeln oder in einen neuen Tab.

## Literatur

[1] D. Becher. DB-Normalizer. TU München, 2021. https:
//db.in.tum.de/teaching/ws2021/grundlagen/.

[2] P. Chen. The-Entity-Relationship-Model. ACM transac-
tions on database systems (TODS), 1976.

[3] H. Faeskorn-Woyke and B. Bertelsmeier. EDB - Das
eLearning Datenbank Portal der TH Köln., 2021.

[4] K. Schneider and F. Keller. Das Daten Café an der Hoch-
schule Harz, 2021. http://datencafe.hs-harz.de/.
