# Dokumentim: Metoda 2 (Alternative) vs Metoda 1

## Qellimi
Metoda 2 eshte krijuar si **zgjidhje alternative krahasuese** ndaj Metodes 1, jo domosdoshmerisht per te arritur score me te larte.

## Cfare forme zgjidhjeje kemi zgjedhur ne Metoden 2
Ne Metoden 2 kemi zgjedhur nje qasje **heuristike te thjeshte me renditje globale sipas kohes se fillimit**:

1. Ndertohet nje liste globale e te gjitha programeve nga te gjitha kanalet.
2. Lista renditet sipas:
   - start me i hershem
   - end me i hershem
   - score me i larte
   - channel_id
3. Ne cdo iterim merret grupi i programeve qe kane **fillimin me te hershem te mundshem** dhe jane te vlefshme sipas kufizimeve.
4. Nga keto kandidate zgjidhet programi me score me te mire lokal, duke llogaritur:
   - score baze i programit
   - bonuset e time preference
   - penalitetin e nderrimit te kanalit
   - penalitetet e tjera sipas util-eve ekzistuese
5. Shtohet nje bonus i vogel "stickiness" (qendrimi ne te njejtin kanal) vetem si rregull i thjeshte stabilizues.
6. Ne rast barazimi perdoret tie-break i lehte me seed (deterministik).

## Krahasimi logjik me Metoden 1

### Metoda 1 (GreedyScheduler)
- Punon ne menyre **minute-by-minute**.
- Ne cdo minute kerkon kanalin/programin me "best fit" ne ate cast.
- E avancon kohen sipas vendimit te marre ose me hap 1 minute kur s'ka zgjedhje.
- Tipi i algoritmit: **Greedy heuristik lokal ne kohe (time-driven greedy)**.

### Metoda 2 (solution_method2)
- Punon me **pool global programesh te renditura paraprakisht**.
- Nuk skanon cdo minute; perqendrohet te **fillimi me i hershem i mundshem** ne secilin hap.
- Ben zgjedhje me heuristic lokal + stickiness bonus + tie-break deterministic.
- Tipi i algoritmit: **Event-driven greedy heuristic (earliest feasible start)**.
- Randomness: perdoret vetem si tie-break shume i vogel me seed fiks (default 42), prandaj rezultati mbetet i perseritshem per te njejtin seed.

## Pse konsiderohet qasje ndryshe
Metoda 2 ndryshon thelbesisht nga Metoda 1 ne menyren e eksplorimit te hapesires se zgjidhjes:
- Metoda 1: orientim ne kohe (minute-by-minute).
- Metoda 2: orientim ne evente/programet e renditura globalisht (earliest feasible start).

Pra, edhe pse te dyja jane heuristike, mekanizmi i selektimit dhe rrjedha e vendimmarrjes jane te ndryshme.

## Formati i output-it
Metoda 2 prodhon output ne **te njejtin format JSON** si Metoda 1, permes te njejtit serializer:
- top-level: `scheduled_programs`
- cdo element: `program_id`, `channel_id`, `start`, `end`

## Ekzekutimi
### Si te ekzekutosh Metoden 1
1. Hap terminalin ne root te projektit.
2. Ekzekuto:
   - python main.py
3. Zgjedh file-in e input-it nga lista.
4. Kur kerkohet scheduler, zgjedh opsionin 1 (GreedyScheduler).

Shembull i rrjedhes:
- Command: python main.py
- Pastaj ne prompt: zgjedh p.sh. toy.json
- Pastaj ne prompt: shkruaj 1

### Si te ekzekutosh Metoden 2
- Me input specifik:
  - python solution_method2.py --input data/input/toy.json
- Me zgjedhje manuale te file-it:
  - python solution_method2.py

### Shembull krahasimi i shpejte
1. Run Metoda 1 me te njejtin input.
2. Run Metoda 2 me te njejtin input.
3. Krahaso file-at e prodhuar ne folderin data/output sipas score ne emer te file-it.

## Implementimi
Implementimi i plote ndodhet ne file:
- `solution_method2.py`
