# <<PAGE:1>>Interaktives Anpassungsfähiges E-Learning-System Im

# Bereich Datenbanken

Fabian Keller
Hochschule Harz
Friedrichstraße 57-59
38855 Wernigerode
fkeller@hs-harz.de

Pia-Katharina Habekost
Hochschule Harz
Friedrichstraße 57-59
38855 Wernigerode
u36775@hs-harz.de

Kerstin Schneider
Hochschule Harz
Friedrichstraße 57-59
38855 Wernigerode
kschneider@hs-harz.de

## ABSTRACT

E-Learning-Systeme finden immer weitere Verbreitung in
den verschiedensten Lehrbereichen. Auch im Bereich Datenbanken
gibt es eine Vielzahl von Anwendungsgebieten.
Es werden zwei Komponenten vorgestellt, die bei der Lehre
im Rahmen von Aufgaben bezogen auf ER-to-Relational-Mapping
und Normalisierung unterstützen sollen. Vielfältige
Interaktionen und Hilfestellungen bspw. Empfehlungen von
multimedialen digitalen Elementen werden zur Verbesserung
des Lernprozesses integriert.

## Keywords

E-Learning-Systeme, ER-to-Relational-Mapping, SQL-DDL,
Normalisierung, Recommender-Systeme

## 1. EINLEITUNG

Der Einsatz von E-Learning-Systemen wird zunehmend
bedeutsamer. Durch Erweiterungen der Interaktions- und
Feedbackmöglichkeiten kann die Nützlichkeit der E-Learning-Systeme
verbessert werden und den Lernenden nicht nur
in Selbstlernphasen Hilfestellungen und Unterstützungsmöglichkeiten
im Lernprozess zur Verfügung stellen. Im Kontext
von Leistungsermittlungen können Hilfestellungen eingeschränkt
werden, trotzdem sollen die Korrektur- und Abfragemöglichkeiten
erleichtert und verbessert sein.

Das Konzept ER-to-Relational-Mapping und die Normalisierung
eines Relationenmodells bzw. relationalen Datenmodells
sind zwei grundsätzliche Gebiete, die in einführenden
Lehrveranstaltung im Bereich Datenbanken behandelt
werden. In den letzten Jahren wurden verstärkt E-Learning-Syteme
eingesetzt, sodass auch diese Gebiete von diesen Systemen
unterstützt werden sollten. Das E-Learning Datenbank
Portal edb-Portal der TH Köln [3] ist ein umfangreiches
E-Learning-Angebot für den Bereich Datenbanken und
enthält auch einen ER-Trainer. An der TU München gibt es
den DB-Normalizer [1].

32nd GI-Workshop on Foundations of Databases (Grundlagen von Datenbanken),
September 01-03, 2021, Munich, Germany.
Copyright © 2021 for this paper by its authors. Use permitted under Creative
Commons License Attribution 4.0 International (CC BY 4.0).

Das E-Learning-System ALEA [4] wird im Bereich Datenbanken
entwickelt, weiterentwickelt und eingesetzt. Es
besteht aus verschiedenen Komponenten, die unterschiedliche
Teilgebiete adressieren. Diese sollen weitestgehend mit
den Lernenden interagieren und Hilfestellungen bereitstellen.
Die typischerweise in einführenden Datenbanklehrveranstaltungen
enthaltenen Aufgaben in den Bereichen ER-to-Relational-Mapping
und Normalisierung sind in der Regel
sehr aufwendig zu korrigieren. Für die Lernenden ist ein
Üben dieser Aufgaben jedoch sehr hilfreich. Für das ALEA-System
wurden daher interaktive Komponenten für die beiden
Bereiche entwickelt und genutzt.

Diese Komponenten und deren vielfältige Interaktionsmöglichkeiten
werden im Folgenden thematisiert. Grundsätzliche
Möglichkeiten zur Interaktion des E-Learning-Systems
werden hierbei veranschaulicht.

Nach einer kurzen Einführung in die grundlegenden Aspekte
des Systems wird auf die Mapping-Aufgaben aus dem
Bereich ER-to-Relational-Mapping eingegangen. Die vielfältigen
Arten der Interaktionen bei der Bearbeitung werden
erläutert. Die Bearbeitung der Normalisierungsaufgaben erfordert
ergänzende Interaktionsmöglichkeiten und Ansichten,
die im folgenden Kapitel beschrieben werden. Schließlich
werden die Ergebnisse zusammengefasst und ein Ausblick
gegeben.

## 2. GRUNDLEGENDE ASPEKTE

Das ALEA-System ist ein datenbankbasiertes E-Learning-System
für Datenbanken und besteht aus verschiedenen Komponenten
für unterschiedliche Bereiche.

Das System wurde hauptsächlich mit Java und JavaScript
entwickelt. Als Entwurfsmuster wurde MVC2 verwendet,
das heißt, es gibt eine logische Trennung zwischen Logik
und Anzeige. Die Anzeige basiert auf HTML5 in Kombination
mit CSS und wurde mit JavaScript erweitert, um die
Interaktionsmöglichkeiten zu erhöhen und verbessern. Mithilfe
von AJAX werden nach Bedarf Daten an den Server
gesendet ohne dass die Webseite neu geladen wird. Zur Verwaltung
der Information über Aufgaben, Lösungen, Lernende
usw. werden Datenbanksysteme eingebunden.

## 3. AUFGABENTYP ER-TO-RELATIONAL-MAPPING

Für die Thematik des ER-to-Relational-Mapping ist ein
Fragentyp vorgesehen, der das Thema der Erstellung von
relationalen Datenmodellen beinhaltet auf Basis vorgegebe-

<<PAGE:2>>ner ER-Modelle und Anforderungen. Aufgaben dieses Typs
beinhalten die Darstellung eines konzeptuellen Datenmodells,
welche als Bild vorliegt, bspw. ein gezeichnetes ERM
in Chen-Notation [2]. Dieses soll von den Lernenden auf ein
logisches Datenmodell, hier ein Relationenmodell, abgebildet
werden. Dazu sollen die Lernenden die entsprechenden
Tabellen und Constraints definieren. Die relevanten Constraints
sind Not Null, Unique, Primary Key und Foreign
Key.

Die Mapping-Aufgaben sind darauf ausgelegt den Lernenden
visuell und interaktiv Wissen zu vermitteln. In diesem
Fall fungiert das System als sog. Composer zur Erstellung
der notwendigen Tabellen. In diesen können durch Schaltflächen
Tabellenbezeichnung, Spalten und Constraints hinzugefügt
werden.

## 3.1 Bearbeitung der Aufgaben

Zur Lösung der Mapping-Aufgaben gibt es für jede Aktion
eine entsprechende Schaltfläche. Das System erlaubt es
den Lernenden nicht mehrere Aktionen parallel auszuführen.
Erst nachdem eine Aktion abgeschlossen ist, kann eine neue
gestartet werden. Für diesen Zweck werden alle anderen Aktionen
durch das Deaktivieren der entsprechenden Buttons
unterbunden (siehe Abbildung 1). Wird zum Beispiel eine
neue Tabelle definiert, so muss für die Tabelle ein Name
eingegeben werden, bevor Spalten hinzugefügt werden können.
Wiederum muss mindestens eine Spalte zu einer Tabelle
gehören damit Constraints erzeugt werden können (siehe
Abbildung 2).

Das konzeptuelle Datenmodell ist in den Aufgabenstellungen
als Bild enthalten. Dieses kann im oberen Bereich des
Systems eingeblendet werden. Damit die Lernenden zu jeder
Zeit einen freien Blick auf das abzubildende ER-Modell
haben, lässt sich dieses durch einen Klick in einem frei beweglichen
modalen Fenster oder einem neuen Tab öffnen.
So besteht die Möglichkeit auch bei größeren Datenmodellen,
bei deren Verarbeitung vermehrt gescrollt werden muss,
den Überblick zu behalten. Zudem kann die Größe des abgekoppelten
Fensters durch Ziehen mit der Maus verändert
werden.

#### Figure 1: Aktive Bearbeitung einer Spalte

## 3.2 Prüfen der Eingaben

Ein wichtiger Aspekt der Mapping-Aufgaben ist es die
Eingaben der Lernenden so früh und umfangreich wie sinnvoll
und möglich zu prüfen. Bereits bei den Eingaben werden
clientseitige Abfragen genutzt, welche durch JavaScript rea-

#### Figure 2: Beispiel von Constraints

lisiert werden. Diese beziehen sich auf grundsätzliche Strukturen
und Regeln bei den Tabellendefinitionen. Weiterhin
kann der äquivalente DDL-Code aus den entstandenen Relationen
erzeugt werden, um eine Prüfung auf dem Datenbankserver
auszuführen. Darüber hinaus können durch die
in der Datenbank zu der Aufgabe hinterlegten Informationen
weitere Prüfungen durchgeführt werden, die sich darüber
hinaus speziell auf die Aufgabe und deren Anforderungen
beziehen. Die Korrektheit einer Lösung kann zwar
generell nicht automatisch entschieden werden, aber Fehler
können weitestgehend erkannt werden. Die Gestaltung der
Aufgaben kann dies erleichtern.

Bereits bei der Eingabe sind ausgewählte Strukturen und
Regeln bezogen auf die Tabellen und Constraints einzuhalten,
sodass diese idealerweise von den Studierenden verinnerlicht
werden.

Der Composer fungiert grundlegend als dynamisch erweiterbares
HTML-Formular. Die durch die Lernenden ausgelösten
Aktionen durchlaufen in dieser Phase nicht jedes Mal
eine Validierungsroutine auf dem Server, wodurch Ressourcen
gespart werden.

Nicht alle logischen Zusammenhänge müssen durch das
eingebundene Datenbanksystem geprüft werden. Ein Beispiel
für diese Art der Prüfung ist die Löschung von Spalten.
Durch eine Routine innerhalb der JavaScript-Skripte
wird geprüft, ob die Spalte für Constraints der aktuellen
oder anderer Tabellen genutzt wird. Ist dies der Fall, gibt
das System eine Meldung aus und der Löschvorgang wird
abgebrochen. Die Umbenennung einer Spalte wird ebenfalls
durch eine JavaScript-Routine geprüft. Dieser Vorgang wird
jedoch innerhalb der aktuellen Tabelle zugelassen und ein
Hinweis ausgegeben der darauf hinweist, dass andere Tabellen
mit dieser Spalte in Zusammenhang stehen könnten,
sodass eine manuelle Prüfung notwendig ist. Die durch die
Änderung des Spaltennamens notwendigen Anpassungen innerhalb
der Tabellendefinition werden automatisch durchgeführt.
Da diese Änderungen die Lernenden von relevanteren
Aspekten ablenken würden.

Das Zulassen von Aktionen trotz Inkonsistenz kann sinnvoll
sein. Ein Beispiel ist ein Fremdschlüssel-Constraint, welcher
angelegt wird bevor die referenzierten Spalten als Kandidatenschlüssel
(Primary Key oder NOT NULL/Unique
Constraints) definiert wurden. Ansonsten würden positive
Aktionen zu stark von erzwungenen Reihenfolgeabhängigkeiten
gestört werden. Die Lernenden können jederzeit den
dem aktuellen Zustand entsprechenden DDL-Code über das
Datenbanksystem prüfen lassen. Für Leistungsbewertungen
kann diese Möglichkeit eingeschränkt werden.

## 3.3 Reaktionen des Systems auf Eingaben

Jede Aktion ruft eine Reaktion hervor. Wenn die Lernenden
als Beispiel eine Spalte umbenennen, werden die Folgen
dieser Aktion in einer Meldung visuell dargestellt, da

<<PAGE:3>>ggfs. Anpassungen aufgrund von Abhängigkeiten in anderen
Tabellen durch die Lernenden notwendig werden können.
Hierbei wird angestrebt, dass diese Meldungen motivierend
und angepasst an die Sprache der Lernenden formuliert werden.
Die Meldungstexte können im System angepasst werden.
Hier bieten sich weitere Möglichkeiten für intelligente
Empfehlungsfunktionen. Die Lernenden dürfen und sollen
Fehler machen aus denen sie lernen können. Das Wissen soll
sich durch Wiederholen verfestigen.

Für die Mapping-Aufgaben sind diese Hinweise vorteilhaft,
um die Übersicht über den aktuellen Bearbeitungsstand
zu erhalten. Die Hinweise zeigen mögliche Komplikationen
auf und sollen so das Verständnis der Lernenden für
logische Zusammenhänge innerhalb des Relationenmodells
erhöhen. Deswegen kann es hilfreich, dass in den Hinweisen
angezeigt wird, dass Änderungen in der aktuellen Tabelle
durchaus Auswirkungen auf die Constraints anderer Tabellen
haben könnten. So sind die Lernenden angehalten diese
aktiv anzupassen.

Die eben genannten Hinweise erscheinen als modale Fenster
mittig in der Browserausgabe, um die Aufmerksamkeit
der Lernenden einzufangen und die Wichtigkeit dieser Änderung
in den Vordergrund zu stellen (siehe Abbildung 3).
Diese Hinweise sollen während der Bearbeitung der Aufgabe
weiterhin zur Verfügung stehen und werden deshalb als
zeitlich sortierte Liste abrufbar über ein ’Notification Icon’
bereitgestellt. Eine Aufteilung der Listen in unterschiedliche
thematische Listen wird nach weiteren Evaluierungen
entschieden. Diejenigen Nachrichten, die seit dem letzten
Öffnen der Liste durch die Lernenden hinzugekommen sind,
werden farblich hervorgehoben.

Der ’Notification Icon’ befindet sich in der Toolbar im
oberen Bereich des Systems.

#### Figure 3: Hinweis zur Umbennung einer Spalte

## 3.4 Die Toolbar

Um den Lernenden weitere Funktionen zur effizienten Bearbeitung
der Aufgabe und Hilfestellungen aufzeigen zu können,
befindet sich am oberen Rand des Systems eine Toolbar
(siehe Abbildung 4). Diese stellt aktuelle Informationen,
Hinweise und Hilfestellungen zur Verfügung. Wie bereits erwähnt
gibt es hier die Auflistung der Hinweise zur Bearbeitung
der aktuellen Aufgabe.

Sind neue Benachrichtigungen eingetroffen, wird an dem
Icon einer Glocke ein roter Kreis angezeigt (siehe Abbildung
4 und Abbildung 5). Neben den Hinweisen zur Bearbeitung
werden unter der Glocke zudem noch Hinweise auf
neue Empfehlungen gegeben. Gibt es zur aktuellen Aufgabe

weiterführende Informationen, so können diese in verschiedenen
medialen Formen, z.B. Screencasts, Podcasts, Hilfetexte,
Hilfegrafiken, vorliegen und abgerufen werden.

Die Farbe der Icons kann, wie auch die Ansprache oder
empfohlene Medien, durch die Empfehlungsalgorithmen angepasst
werden.

Neben diesen Hinweisen werden zudem noch Informationen
zum aktuellen Bearbeitungsstand der Aufgabe gegeben.
Diese Informationen finden die Lernenden unter dem Info-Icon
(siehe Abbildung 5).

Wenn bspw. die Lösung bzw. die gültigen Lösungen der
Aufgabe eine bestimmte Anzahl an Uniques erfordern oder
eine minimale oder maximale Anzahl an Uniques enthalten
dürfen, kann den Lernenden mitgeteilt werden, dass die
Anzahl der Uniques noch nicht einer gültigen Lösung entspricht.
Hierbei wird den Lernenden in der Regel keine konkrete
Anzahl genannt, lediglich dass diese noch nicht gültig
ist.

Zudem können hier Hilfetexte erscheinen, die sich auf die
Arbeitsweise der Lernenden beziehen. Bemerkt das System
z.B. dass es im Bereich der Foreign Key Constraints zu
vermehrten Interaktionen kommt, können hier Definitionen
oder Tipps zum Thema Foreign Key Constraints angezeigt
werden. Dies ist abhängig von den eingesetzten hybriden
Filter- und Empfehlungsalgorithmen.

Um den Lernenden eine sog. ’Quick View’ über den aktuellen
Bearbeitungsstand zu geben, befinden sich in der Toolbar
kleine Icons, welche repräsentativ für Elemente der Modellierung
stehen. Dies sind von links nach rechts die Gesamtanzahl
der aktiven Tabellen, der aktiven Spalten, der Primary
Key Constraints, der Unique Constraints, der Foreign Key
Constraints und der NOT NULLs außerhalb von Primary
Key Constraints (siehe Abbildung 4). Durch die Übersicht
der aktuell aktiven Elemente sollen die Lernenden eine kompakte
Übersicht über den aktuellen Zustand erhalten. Insbesondere
in Übungsphasen, in denen die Mindestanzahl oder
die exakte Anzahl der benötigten Elemente vorgegeben sein
kann, ist diese Ansicht hilfreich um zu eruieren, wie weit
sich das eigene Ergebnis vom gesuchten zumindest in diesen
Aspekten unterscheidet.

#### Figure 4: Toolbar mit Benachrichtigungshinweis

#### Figure 5: Toolbar mit geöffneten Benachrichtigungen

## 3.5 Feedback durch die Lernenden

Damit die Kommunikation und Interaktion der Lernenden
sich nicht nur auf das System und dessen Hinweise bezieht,
gibt es die Schaltfläche ’Question and Feedback’. Hier können
die Lernenden Kontakt zu den Lehrkörpern aufnehmen.
Hierbei wird zwischen aufgabenpezifischen Fragen und Feedback
unterschieden. Vor allem das Feedback ist gewünscht,

<<PAGE:4>>da dieses dazu dient, das System an die Bedürfnisse der Lernenden
anzupassen und eine kontinuierliche Verbesserung
voranzutreiben (siehe Abbildung 6).

#### Figure 6: Feedbackfenster

## 3.6 Mediale Hilfestellungen

Für die Lernenden stehen verschiedene Arten von medialen
Hilfestellungen zur Verfügung, die ständig ergänzt,
produziert und weiterentwickelt werden. Dabei handelt es
sich um digitale Medien wie bspw. Screencasts, Erklärvideos,
Podcasts, Hilfetexte und Hilfegrafiken. Diese Medien
werden kurz gehalten und sind thematisch nicht voneinander
abhängig, können sich aber ergänzen und werden ggf. in
Gruppen mit oder ohne empfohlener Reihenfolge empfohlen.

Über die Icons auf der linken Seite können aktuell bereitgestellte
Medien abgerufen werden. Die Medien werden
in modalen Fenstern innerhalb der Anwendung aufgerufen.
Für die Icons gibt es zwei Bereiche. Die grauen Icons beinhalten
vordefinierte Hilfestellungen, wohingegen die grünen
Icons aktuell empfohlene Hilfestellungen beinhalten.

### 3.6.1 Screencasts und Erklärvideos

Screencasts befassen sich mit der Anwendung und Nutzung
von Software bzw. mit den Erklärungen zu Lösungen
dieser Aufgabentypen. Für die Aufgaben zum ER-to-Relational-Mapping
wurden bereits mehr als 50 Screencasts
produziert.

In kurzen aber prägnanten Videos werden den Lernenden
Inhalte aus dem Bereich vermittelt. Diese Screencasts
können sich auf Aufgaben beziehen oder allgemeine Vorgehensweisen
und Hinweise enthalten. Neben den Screencasts
finden die Lernenden hier zudem Erklärvideos die allgemeine
Prinzipien von Datenbanken thematisieren.

### 3.6.2 Podcasts

Podcasts sollen, so wie die Screencasts, kompakt Informationen
vermitteln. Die Themen können hier sowohl Aufgaben-
oder Challenge-bezogen als auch allgemeingültig sein. Die
Podcasts sind Dialoge zwischen zwei oder mehreren Sprechenden,
die ein Thema diskutieren, um den Lernenden neue
Anreize zu bieten über das Gehörte nachzudenken. Auch
Hilfetexte könnten vorgelesen werden.

### 3.6.3 Hilfetexte

Das System ist auch darauf ausgelegt, dass die Lernenden
gegebenenfalls nicht die Möglichkeit haben Audio- oder
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
Systems, zu der aktuellen Situation und zur Aufgabe Hilfestellungen
empfohlen. Diese können sich dynamisch anpassen
und müssen nicht permanent verfügbar bleiben. Empfehlungen
können entfernt werden, wenn bspw. Lernende die
Aufgabe wechseln oder sich der Fokus der Thematik ändert.

Vordefinierte Inhalte beziehen sich nicht zwingend auf eine

Aufgabe im Einzelnen. Sie können Informationen betreffen,
die wichtig sind um ein Grundverständnis für die Kursinhalte
zu erlangen. Auch wenn keine Challenges aktiv sind,
können Inhalte bereit gestellt werden.

Die Gesamtheit der multimedialen Inhalte wird nicht nur
im Rahmen der Aufgaben genutzt. Mit den Inhalten werden
Playlisten gefüllt, die den Lernenden zur Verfügung stehen
um die Selbstlernphase zu unterstützen.

### 3.6.6 Empfehlungen

Hilfestellungen und multimediale Elemente sollen zudem
zunehmend vom System empfohlen werden. ALEA nutzt
verschiedene Arten von Empfehlungsalgorithmen, die ständig
weiterentwickelt werden. Diese werden mit wachsender
Nutzung und Datenmenge ausgebaut und verbessert.

### 3.6.7 Metadaten

Ein wichtiger Aspekt für die Zuweisung der medialen Hilfestellungen
sind die hinterlegten Metadaten. Für mediale
Inhalte werden eine Reihe von Metadaten definiert, die es
den Empfehlungsalgorithmen erlauben, die Inhalte den Lernenden
zuzuordnen. Diese werden auch bei der Erstellung
von Aufgaben bzw. zur Zuordnung von Aufgaben im Rahmen
von Challenges zu Lernenden oder Gruppen von Lernenden
genutzt. Dies ermöglicht im Vorfeld die Zuordnung
der Hilfestellung zu Aufgaben. Ein direkt für diese Aufgabe
produzierter Podcast, soll in der Regel nicht als Hilfestellung
empfohlen werden.

## 3.7 Check and Submit

Um sich den zugehörigen SQL-Code anzeigen zu lassen
und zur Kontrolle der eigenen Eingaben, steht den Lernenden
im unteren Bereich des Systems die Schaltfläche ’Check
Input and Show SQL’ zur Verfügung. Zum Erzeugen des
SQL-Codes wird die Check-Funktion durchlaufen. Diese baut
zwei Zeichenketten zusammen. Die erste Zeichenkette kann
direkt auf der Datenbank ausgeführt werden. Genutzt wird
diese für den Test, den die Lernenden während der Bearbeitung
machen können und zudem für die finale Abgabe der
Aufgabe. Eine zweite Zeichenkette wird erzeugt und beinhaltet
HTML-Code. Dieser wird zur visuellen Darstellung
des SQL-Codes für die Lernenden genutzt.

#### <<PAGE:5>>Figure 7: Challenge Auswahl und Hilfemedien

Die Ansicht des DDL-Codes soll den Lernenden einen anderen
Blick auf die eigene Lösung verschaffen (siehe Abbildung
8). Damit soll der Bezug zwischen der Planung des Relationenmodells
und dem Verständnis der Syntax der DDL-Befehle
(Data Definition Language) gestärkt werden.

Da die Datentypen für die Lösung der Aufgabe nicht relevant
sind, wird auf dem Datentyp ’variable character’ abgebildet,
der dem Datenbanksystem entspricht auf dem der
Code ausgeführt wird. Um den Lernenden die Möglichkeit
zu bieten den entstandenen DDL-Code zu nutzen, gibt es die
Schaltflächen ’Copy Code’ und ’Save to Script’. ’Copy Co-

de’ kopiert den angezeigten SQL-Code in die Zwischenablage
und ’Save to Script’ bietet die Möglichkeit den Code als Datei
lokal zu speichern. Damit der bereitgestellte SQL-Code
von den Lernenden auf unterschiedlichen Datenbanksystemen
genutzt werden kann, können diese den entsprechenden
Datentyp auswählen.

Die Lernenden haben die Möglichkeit mit der Schaltfläche
’Test on Database’ den ihren Eingaben entsprechenden
DDL-Code direkt auf dem angebundenen Datenbanksystem
zu testen. Die Rückmeldung wird in dem Check-Input-Ausgabefenster
ausgegeben. Hierbei wird einerseits getestet,
ob die Eingaben der Lernenden einen gültigen SQL-Code
entsprechen. Andererseits wird die Lösung unter Verwendung
der zur Aufgabe hinterlegten Informationen weitestgehend
durch das System ausgewertet. Korrekte Lösungen
von Aufgaben können u. a. eine vorgegebene Anzahl von
Tabellen, Spalten, Constraints (Primary Keys, Uniques, Not
Nulls außerhalb von Primary Keys, Foreign Keys) und darin
enthaltene Attributanzahl bzw. eine jeweilige Mindest-
und Maximalanzahl erfordern, so dass Lösungen als falsch
erkannt werden können.

Die Auswertung der Aufgabe bzgl. der Sinnhaftigkeit der
Bezeichnungen bspw. von Tabellen oder Spalten, kann und
wird dabei nicht geprüft. Jedoch kann über das Datenbanksystem
eine weitergehende Prüfung abhängig von vorliegenden
Daten zur Aufgabe durchgeführt werden.

Die Ausgabe einer Zwischenauswertung ohne wiederholte
Serveranfrage in der Toolbar ist möglich, wenn die Information
zu gültigen Lösungsmöglichkeiten der Aufgabe bezogen
auf die Anzahl der Elemente eindeutig ist und Variationen
nur begrenzt möglich sind. In der Datenbank können
auch Angaben für Aufgaben mit verschiedenartigen Lösungen
hinterlegt und ausgewertet werden. Insbesondere wenn
die Aufgabenstellungen komplexer werden, können die Auswertungen
aufwändiger werden. Je nachdem wie die Lernenden
ihre Lösungen aufbauen kann sich bspw. die Anzahl der
Elemente in einem Constraint unterscheiden und trotzdem
eine richtige Lösung erzeugen.

#### Figure 8: Ausgabe des SQL-Codes und Rückmeldung der Datenbank

Die Schaltfläche ’Submit’ führt die Lernenden zur Abgabe
ihrer Lösung. Zur Sicherheit und um Fehlklicks abzufangen
öffnet sich, nachdem die Lernenden auf ’Submit’ gedrückt
haben, ein weiteres Fenster. In diesem erhalten die Lernenden
die Information, ob ihre Lösung eine gültige Lösung sein

<<PAGE:6>>könnte. Ist dies der Fall, besteht die Möglichkeit die Aufgabe
abzugeben.

In Lernphasen können die Lernenden unfertige Aufgaben
zur späteren Bearbeitung überspringen. Anstatt einer möglichen
Ja/Nein-Abfrage, ob die Aufgabe abgegeben werden
soll, kann zwischen ’Zurück zur Bearbeitung’ oder ’ Überspringen’
(siehe Abbildung 9) gewählt werden. Diese unfertigen
Aufgaben werden nicht aus dem System entfernt.
Aufgaben die als Lern- oder Testataufgaben gelten müssen
solange wiederholt werden, bis die Eingabe gültig ist. In der
Abbildung 7 ist zu sehen, dass eine Challenge Aufgaben zur
Auswahl der Bearbeitungsreihenfolge beinhalten kann. Eine
Challenge bleibt bestehen bis alle Aufgaben erfolgreich
bearbeitet wurden.

#### Figure 9: Abgabe einer Lernaufgabe

## 3.8 Prüfungsmodus

Das System ist zum einen für die Lernphase und zum
anderen für die Prüfungsphase gedacht. Hierfür sieht das
System vor, dass Funktionen, welche für Lernphasen wichtig
sind, für die Prüfungen deaktiviert werden. Die Hilfestellungen,
die sich auf Informationen zu gültigen Lösungen
beziehen, sind nicht verfügbar. Empfehlungen und alle damit
verbundenen Hilfsmedien sind ebenfalls nicht erreichbar.
In dem Fenster ’Check Input und Show SQL’ werden
die Schaltflächen auf ’Close’ und ’Submit’ reduziert. Eine
zweistufige Abfrage nach dem ’Submit’ bleibt zwar bestehen,
jedoch wird das erscheinende Fenster auf eine erneute
Frage, ob die Lösung abgegeben werden soll, reduziert.

## 4. AUFGABENTYP NORMALISIERUNG

Ein weiterer Aufgabentyp des ALEA-Systems ist die Normalisierung.
Dieser Aufgabentyp nutzt die Grundfunktionen
der Mapping-Aufgaben, da Tabellen und Constraints definiert
werden müssen.

In einer Aufgabenstellung zur Normalisierung erhalten die
Lernenden eine oder mehrere Tabellen sowie eine Äquivalenzmenge
zu der Menge aller für die Tabellen gültigen Funktionalen
Abhängigkeiten. Die Normalform der Tabellen ist
anzugeben. Die Tabellen sind unter Verwendung des Zerlegungsverfahrens
in der Regel in 3NF zu überführen, sofern
sie sich nicht in der dritten Normalform befinden. Die Tabellen
können in der Aufgabenstellung zur Verdeutlichung
mit Daten gefüllt sein. Zur besseren Übersicht lassen sich
die Inhalte der Tabellen bei Bedarf aus- und einblenden.
Die Darstellung der funktionalen Abhängigkeiten lässt sich,
wie auch beim ALEA-Mapping das vorgegebene Datenmodell,
durch einen Klick in ein bewegliches, modales Fenster
umwandeln oder in einen neuen Tab.

## 4.1 Erweiterte Tabellenansicht

Für die Bearbeitung der Aufgaben zur Normalisierung
wurden die Bereiche zur Definition der Tabellen durch Funktionen
ergänzt (siehe Abbildung 10). Neben den bekannten
Funktionen der Benennung, Löschung und Hinzufügen von
Spalten und Constraints, gibt es eine Schaltfläche zur Deaktivierung
der Tabelle. Sobald eine Tabelle zerlegt werden
soll, muss sie deaktiviert werden. Sie wird nicht entfernt,
damit der Verlauf nachvollziehbar bleibt. Die durch die Zerlegung
neu entstehenden Tabellen müssen eingeben werden.
Dabei soll über ein Dropdown-Menü, welches alle inaktiven
Tabellen auflistet, angegeben werden, aus welcher Tabelle
eine Tabelle jeweils entstanden ist.

#### Figure 10: Tabellendefinition mit erweiterten Funktionen

#### Figure 11: Tabellendefinition finalisieren

Die Studierenden sollen für jede neu entstandene Tabelle
die Normalform angeben. Dazu befindet sich ein Auswahlfeld
im Kopfbereich der Tabellendefinition. Die Lernenden
sollen zudem jeweils zu jeder Zerlegung angeben, aus welchen
Gründen diese durchgeführt werden musste. Dazu befindet
sich ein Textfeld im Fußbereich der Tabellendefinition.
Zudem ist es erwünscht hier weitere Anmerkungen, Fragen,
Notizen und Feedback der Lernenden zu erhalten. Sobald
für eine Tabelle die geforderte Normalform erreicht wurde,
soll die Tabelle finalisiert werden (siehe Abbildung 11).

## 4.2 Erweiterte Ansichten

Die Komponente für die Aufgaben zur Normalisierung
wird durch eine weitere ’Quick View’ ergänzt. Auf der rechten
Seite finden die Lernenden eine Übersicht über die aktuell
aktiven und inaktiven Tabellen. Neben dem Tabellennamen
sind hier auch die Spaltennamen gelistet. Ebenso können
die Begründungen angezeigt werden.

## 5. ZUSAMMENFASSUNG UND AUSBLICK

Komponenten zur Bearbeitung von Aufgaben zum ER-to-Relational-Mapping
und zur Normalisierung werden dargestellt.
Vielfältige Interaktionen und Hilfestellungen bspw.
Empfehlungen von multimedialen digitalen Elementen werden
zur Verbesserung des Lernprozesses integriert. Durch
verstärkte Nutzung der Komponenten und dem Anwachsen
der Daten können Empfehlungen und Learning Analytics
weiter verbessert werden.

## Literatur

[1] D. Becher. DB-Normalizer. TU München, 2021. https:
//db.in.tum.de/teaching/ws2021/grundlagen/.

[2] P. Chen. The-Entity-Relationship-Model. ACM transactions
on database systems (TODS), 1976.

[3] H. Faeskorn-Woyke and B. Bertelsmeier. EDB - Das
eLearning Datenbank Portal der TH Köln., 2021.

[4] K. Schneider and F. Keller. Das Daten Café an der Hochschule
Harz, 2021. http://datencafe.hs-harz.de/.
