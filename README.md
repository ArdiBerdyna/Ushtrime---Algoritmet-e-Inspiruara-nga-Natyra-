<div align="center">

<!-- Logo: direct SVG from Commons. If it does not load (firewall, rate limits), download the file from the Commons link below, save as docs/images/university-of-prishtina-logo.png in this repo, and point src to that path. -->
<img src="https://upload.wikimedia.org/wikipedia/commons/e/e1/University_of_Prishtina_logo.svg" width="150" height="150" alt="University of Prishtina logo" />

# University of Prishtina

## Fakulteti i Inxhinierisë Elektrike dhe Kompjuterike

**Programi i Studimit:** Inxhinieri Kompjuterike dhe Softuerike – Master  
**Lënda:** Algoritmet e Inspiruara nga Natyra  
**Grupi:** 13  

</div>

---
 
 # Optimizimi i orarit të programeve TV (Python)

Implementimi kryesor në rrënjën e repozitoriumit përfshin parserin, validatorin dhe disa heuristika për përzgjedhjen e programeve. **Metoda 2** (`solution_method2.py`) është një **algoritem gjenetik** që përdor kromozomë me gjene për program (pesha `[0,1]`), crossover uniform dhe mutacion me `mutation_rate`.

### Ku ruhen skedarët e daljes (Metoda 2)

| Mënyra | Dosja | Sa skedarë për një instancë |
|--------|-------|------------------------------|
| **`python solution_method2.py`** (pa `-i`): zgjedh vetëm instancën nga lista | **`data/parameter_study_outputs/`** (ose `--parameter-study-dir`) | **10 output JSON** për atë instancë — një për çdo ekzekutim GA (**parazgjedhje `N=10`**; ndrysho me `--runs` para komandës). Emër shembull: `australia_iptv_run_03_score_2827.json`. |
| **`python solution_method2.py -i …`** | **`data/output/`** | **1** skedar për një ekzekutim të vetëm GA (sjellja klasike). |
| **`--parameter-study-one`** / **`--parameter-study`** (studimi me 3 kombinime) | **`data/parameter_study_outputs/`** | **30 skedarë** për instancë nëse `--runs 10`: **3 kombinime × 10 ekzekutime**; emra me **`_cfg_0` … `_cfg_2`**. |

Pra: për **modin interaktiv të thjeshtë**, në **`parameter_study_outputs`** priten **saktësisht 10 skedarë për secilën instancë** që zgjedh (nëse nuk ndryshon `--runs`).

## Parametrat e GA në `solution_method2.py`: roli, rëndësia dhe ndikimi në score

**Score-i** që raporton skripti është **`total_score`**: shuma e fitness-eve të programeve në orarin e ndërtuar (më i lartë = më mirë). Parametrat nuk hyjnë drejtpërdrejt në këtë shumë; ata ndikojnë **se si kërkohet** zgjidhja (popullsia, brezat, si përzihen/mutohen gjenet, sa zgjedhja varet nga gjenet vs nga fitness-i “i vërtetë”).

| Parametri | Roli kryesor | Rëndësia praktike | Si mund të reflektohet në score |
|-----------|--------------|-------------------|----------------------------------|
| **`population_size`** | Numri i kromozomëve paralelisht në çdo brez. | **I lartë** për hapësira të mëdha: më shumë diversitet fillestar dhe më pak “mbetje” në optimum lokal të keq. | Popullsie shumë të vogël → më pak kombinime gjesh për të njëjtin numër brezash → score më i ulët është i mundur. |
| **`generations`** | Sa herë përsëritet evoluimi (selektim → crossover → mutacion). | **I lartë** së bashku me popullsinë: më shumë kohë kërkimi; duhet balancë me kohën e ekzekutimit. | Pak breza → GA nuk arrin të përmirësojë mjaftueshëm → score më i ulët. |
| **`mutation_rate`** | Gjasat që çdo gen të ridizajnohet me vlerë të re `[0,1]`. | **E ndërmjetme**: shumë i lartë → “zhurmë”, prish struktura të mira; shumë i ulët → eksplorim i dobët. | Mutacion i tepërt mund të ulë stabilitetin; i tepër i ulët mund të ngurtësojë individë të dobët. |
| **`crossover_rate`** | Gjasat që dy prindër të kryqëzohen (uniform); përndryshe kopjohen. | **E mesme**: crossover përzihet informacion midis individëve të mirë; nëse është shumë i ulët, popullsia mbetet më “klonuese”. | Crossover i ulët → më pak kombinime të reja nga prindërit e mirë → mund të ketë stagnacion ose score më të ulët. |
| **`gene_bonus_scale`** | Shkallëzon ndikimin e **peshës së gjenit** në përzgjedhjen e programit gjatë dekodimit (`gene × scale`). | **Shumë i rëndësishëm** për këtë implementim: kur është i vogël, zgjedhja i përngjan greedy-së (fitness dominon); kur është i madh, kromozomi **orienton fort** zgjedhjen midis kandidateve të ngjashëm në fitness. | Vlera ekstreme mund të **devijojnë** zgjedhjen nga alternativa me fitness më të mirë → score mund të ulet ose të rritet sipas instancës. |
| **`tournament_size`** | Sa individë hyjnë në turnir për të zgjedhur një prind; më i madh → presion më i fortë drejt individëve më të mirë. | **E mesme**: turnir i vogël (p.sh. 2) → më shumë rrjedhje gjesh të dobëta; i madh → përzgjedhje më “elitare”, por më pak diversitet në prindërit. | Me të njëjtën farë, ndryshimi i turnirit mund të ndryshojë cilët individë mbijetojnë → score ndryshon. |

**Të tjerë të lidhur:** `seed` përcakton riprodhueshmërinë (tie-break, mutacion, crossover); **`run_time_limit`** (nëse përdoret) mund të ndalë GA para përfundimit të plotë të brezave → score më i ulët në instanca të mëdha.

### Shembull eksperimenti (vetëm dokumentim — **parazgjedhjet në kod nuk u ndryshuan**)

Input: **`data/input/australia_iptv.json`**, **`--seed 42`** për të gjitha provat. Komanda bazë:

`python solution_method2.py -i data/input/australia_iptv.json --seed 42 …`

Vlerat e **`total_score`** pas një ekzekutimi për secilin rast:

| Çfarë ndryshoi krahasuar me default-un CLI | `total_score` |
|-------------------------------------------|---------------|
| Parazgjedhje (`--population 24`, `--generations 25`, `mutation 0.08`, `crossover 0.9`, `gene-bonus-scale 50`, `tournament-size 3`) | **2675** |
| Kërkim i **dobët**: `--population 8 --generations 5` | **2564** |
| Kërkim i **thelluar**: `--population 48 --generations 50` | **2827** |
| Mutacion **i lartë**: `--mutation-rate 0.35` | **2669** |
| Mutacion **i ulët**: `--mutation-rate 0.02` | **2675** |
| Crossover **i ulët**: `--crossover-rate 0.25` | **2676** |
| **`gene_bonus_scale` i ulët**: `--gene-bonus-scale 10` | **2577** |
| **`gene_bonus_scale` i lartë**: `--gene-bonus-scale 120` | **2871** |
| Turnir **i vogël**: `--tournament-size 2` | **2675** |
| Turnir **i madh**: `--tournament-size 8` | **2827** |

**Lexim i shkurtër:** në këtë instancë dhe farë, **rritja e popullsisë/brezave** dhe **rritja e `gene_bonus_scale`** / **turnirit** ndihmuan score-in më shumë se opsioni minimal i kërkimit; **`gene_bonus_scale` i ulët** e ul score-in dukshëm sepse gjenet nuk ndihmojnë mjaftueshëm në diferencimin midis programeve të ngjashëm. Rezultatet **nuk janë universale**: në një instancë tjetër ose farë tjetër renditja mund të ndryshojë — prandaj përdoren studimet me shumë ekzekutime më poshtë.

### Si ndikon ndryshimi i parametrave në `total_score`

Parametrat **nuk mbledhen në formulën e score-it**; ata ndikojnë **cilët programe futen në orar** gjatë dekodimit të kromozomit dhe **sa mirë GA arrin të gjente gjene** që mbështesin zgjedhjet me fitness të lartë. Prandaj efekti në score është **i tërthortë**: ndryshon **lista e programeve të planifikuar** → ndryshon **shuma e fitness-eve** (`total_score`).

| Si ndryshon parametri | Ndikimi tipik në score | Çfarë ndodhi në shembullin `australia_iptv` / `seed 42` |
|-------------------------|-------------------------|--------------------------------------------------------|
| **↑ `population_size` dhe/o `generations`** | Më shumë mundësi për të **përparuar** gjenerata dhe për të **mos ngelë** te një orar i dobët; zakonisht më mirë në instanca të pasura me alternativa. | **2675 → 2827** (+152): version “thellë” gjeti orar më të mirë se version i dobët. |
| **↓ `population_size` dhe/o `generations` shumë** | Kërkim i **shkurtër** → mund të humbet kombinim gjesh që sjell më shumë pikë. | **2675 → 2564** (−111): më pak breza dhe më pak individë → score më i ulët. |
| **↑ `mutation_rate`** | Më shumë **zhurmë**: mund të **hapë** zgjidhje të reja ose të **prishë** gjene të mira; efekti në score është **jo monoton**. | **2675 → 2669** (−6): në këtë provë mutacioni më i lartë pak e përkeqësoi rezultatin krahasuar me default-in. |
| **↓ `mutation_rate`** | Më pak eksplorim; nëse popullsia përgjegjet mirë, mund të **ruhet** cilësia; mund të **ngurtësohet** në optimum lokal. | **2675 → 2675** (0): te ky eksperiment nuk ndryshoi score-i krahasuar me default-in. |
| **↓ `crossover_rate`** | Më pak **përzierje** gjenesh midis individëve të mirë → më pak kombinime të reja; shpesh stagnacion ose rrënje e lehtë e score-it. | **2675 → 2676** (+1): ndryshim minimal në këtë farë (mund të jetë brenda variacionit të tie-break). |
| **↓ `gene_bonus_scale`** | Zgjedhja bazohet më shumë në **fitness të drejtpërdrejtë**, më pak në **vektorin e gjenit**; në këtë GA, nëse gjenet nuk diferencojnë kandidatët mirë, mund të **humbet orari më i mirë**. | **2675 → 2577** (−98): ndikimi më i fortë negativ në tabelë për këtë instancë. |
| **↑ `gene_bonus_scale`** | Gjenet **përfshihen më fort** në konkurrencën midis programeve të njëjtës “fare”; mund të **orientojë** dekodimin drejt orareve më të favorshme nёse evoluimi prodhon gjene të përshtatshme. | **2675 → 2871** (+196): rritja më e madhe pozitive në të njëjtën provë. |
| **↑ `tournament_size`** (p.sh. nga 3 në 8, me të njëjtën farë) | **Seleksion më i ashpër** për prindër: më shpesh fitojnë individët me score më të lartë në turnir → evoluimi mund të **përshpejtojë** përmirësimin e popullsisë (ose të reduktojë diversitetin). | **2675 → 2827** (+152) kur `--tournament-size 8` (default i provës: `3`). |
| **↓ `tournament_size`** (p.sh. nga 3 në 2) | Më shumë **harbutësi** në zgjedhjen e prindit → më shumë gjene “të rastit” në turnir; ndonjëherë më pak presion elitar. | **2675 → 2675** (0): në këtë farë kalimi **3 → 2** nuk ndryshoi `total_score` (orari më i mirë mbeti i njëjtë). |

**Shënim:** efektet varen nga **instanca dhe fara**; në një skenar tjetër `tournament-size` 2 mund të ndryshojë score-in nga 3.

**Përmbledhje:** ndryshimi i parametrave ndikon në score **vetëm** duke ndryshuar **zgjidhjen** (progresioni i programeve), jo duke ndryshuar një formulë të përbashkët të pikëve. Prandaj rrjedha është gjithmonë: **parametra të rinj → evoluim/dekodim tjetër → `total_score` tjetër**.

## Studimi i parametrave (GA – Metoda 2)

### Metodologji

- **Kombinime parametrash:** përdoren **tre** grupe të paracaktuara (`PRESET_PARAMETER_SETS` në `solution_method2.py`).
- **Instanca:** 10 skedarë të parë të renditur alfabetikisht në `data/input/*.json` (lista aktuale fillon me `australia_iptv.json` … deri te `spain_iptv.json` për 10 instanca).
- **Përsëritje:** **10 ekzekutime** për çdo instancë dhe për çdo kombinim (gjithsej `3 × 10 × 10 = 300` ekzekutime).
- **Fara:** `run_seed = base_seed + config_idx·1_000_000 + file_idx·10_000 + run_idx` me `base_seed=42`.
- **Kufiri kohor:** studimi përdor një kufi të përgjithshëm `--max-runtime` (sekonda) që ndahet dinamikisht midis ekzekutimeve të mbetura (si në `--benchmark-10x10`).

**Skedarët e ruajtur (10 output për secilin input, për secilin kombinim parametrash):** të gjitha në **një dosje të vetme** — **`data/parameter_study_outputs/`** (ose `--parameter-study-dir`). Emri i skedarit: **`{instancë}_score_{pikë}_run_{XX}_cfg_{i}.json`** — instanca dhe score janë në emër; `run` dhe `cfg` (0, 1, 2 për tre kombinimet) shmangin përmbivendosjen kur ka shumë ekzekutime ose të njëjtin score. JSON: vetëm `scheduled_programs` si në `data/output`. `--no-save-parameter-runs` çaktivizon shkrimin.

### Mënyra interaktive (zhgjidh instancën → 10 output-e në sfond)

```powershell
cd <rrënja e projektit>
python solution_method2.py
```

1. Zgjidh skedarin nga lista (`data/input`).
2. Automatikisht niset një **proces i veçantë** që ekzekuton **GA me parametrat aktualë** (**parazgjedhje `N=10`** ekzekutime; ndrysho me `python solution_method2.py --runs 15` para se të hapet lista). Çdo ekzekutim ruan një JSON në **`data/parameter_study_outputs/`** me emër **`{instancë}_run_XX_score_<pikë>.json`**. Terminali kthehet menjëherë (procesi punon në sfond).

**Një GA i vetëm + `data/output`:** përdor input eksplicit, p.sh. `python solution_method2.py -i data/input/toy.json`.

**Studimi me 3 kombinime parametrash:** `python solution_method2.py --parameter-study-one path/to/instance.json` (ose `--parameter-study` për shumë instanca).

### Ekzekutimi i studimit (të gjitha instancat njëherësh)

```powershell
cd <rrënja e projektit>
python solution_method2.py --parameter-study --input-dir data/input --instances 10 --runs 10 --max-runtime 7200 --seed 42
```

### Kombinimet e parametrave

| Kodi | Emri | Popullsia | Breza | Mutacion | Crossover | `gene_bonus_scale` | `tournament_size` |
|------|------|-----------|-------|----------|-----------|----------------------|---------------------|
| A | `A_balanced_default` | 24 | 25 | 0.08 | 0.90 | 50 | 3 |
| B | `B_exploration_heavy` | 40 | 40 | 0.15 | 0.85 | 80 | 5 |
| C | `C_exploitation_fast` | 16 | 15 | 0.05 | 0.95 | 30 | 2 |

- **A** përfaqëson balancën e parazgjedhur të implementimit.
- **B** rrit eksplorimin (popullatë dhe breza më të mëdhenj, mutacion më i lartë, turnir më i gjerë, bonus gjenetik më i fortë).
- **C** thekson shfrytëzimin e shpejtë (parametra më të vegjël, mutacion i ulët, crossover i lartë).

### Rezultate përmbledhëse (ekzekutim i raportuar)

Parametrat e mësipërm, **10 instanca**, **10 ekzekutime** për instancë, `--max-runtime 7200`, `--seed 42`.

- Koha e përgjithshme e studimit: **~1503 s** (~25 min).
- **Mesatarja e të gjitha ekzekutimeve** (300 pikë rezultatesh):  
  - **A_balanced_default:** 2097.11  
  - **B_exploration_heavy:** 2223.74  
  - **C_exploitation_fast:** 1981.18  

### Si ndikuan të tre kombinimet në score (interpretim nga të njëjtit eksperiment)

Score-i është **shuma e fitness-eve** të programeve të planifikuar (`total_score`); më i lartë = më mirë.

| Krahasim | Mesatarja globale (100 ekzekutime / kombinim) | Ndikimi i përgjithshëm |
|----------|-----------------------------------------------|------------------------|
| **B** vs **A** | 2223.74 vs 2097.11 (**+~126**, ~**+6%**) | Rritje të qëndrueshme të mesatares. |
| **C** vs **A** | 1981.18 vs 2097.11 (**−~116**, ~**−5.5%**) | Ulje të mesatares globale. |
| **B** vs **C** | 2223.74 vs 1981.18 (**+~243**, ~**+12%**) | B qartë më mirë se C në këtë setup. |

**A (`A_balanced_default`)** — sjellje bazë: mesatarja del në mes të treve; në shumë instanca është më mirë se C, më pak optimale se B për **mean** dhe shpesh edhe për **best**.

**B (`B_exploration_heavy`)** — popullatë dhe breza më të mëdhenj, mutacion më i lartë, `gene_bonus_scale` më i madh dhe turnir më i gjerë:
- **Në këto të dhëna**, mesatarja sipas instancës ishte **më e lartë se A në 9 nga 10 instanca** (te `germany_tv_input.json` mesatarja dhe “best” mbetën të barabarta me A dhe B: **932**, pra nuk pati përfitim të dukshëm nga eksplorimi shtesë).
- Instancat me diferencë më të madhe pozitive B−A në **mean** përfshijnë p.sh. `singapore_pw.json`, `australia_iptv.json`, `canada_pw.json`, `spain_iptv.json` — këtu më shumë kërkim dhe diversitet në popullatë përputhet me **score më të lartë mesatar dhe “best” më të lartë**.

**C (`C_exploitation_fast`)** — pak individë/breza, mutacion i ulët, `gene_bonus_scale` i vogël:
- Mesatarja **ra krahasuar me A** në pothuajse të gjitha instancat; **best** shpesh më i ulët (p.sh. `spain_iptv.json`, `singapore_pw.json`, `croatia_tv_input.json`).
- **Std** te disa instanca (p.sh. `germany_tv_input.json`) u rrit — konfigurimi i “shpejtë” **nuk konsolidon** një zgjidhje të vetme të mirë, por prodhon më shumë variacion kur hapësira është e vështirë.
- Intuitivisht: GA i shkurtër **eksploron më pak** se A/B; zgjedhja mbetet e varur nga gjenet dhe farat, por **më pak përmirësime gjatë evoluimit**, ndaj dhe score-i mesatar zakonisht ulet.

**Përmbledhje:** për këtë problem dhe këtë kufi kohor/plan eksperimenti, **parametrat “eksplorues” (B)** përputhen me **score më të lartë**; **parametrat “të shpejtë” (C)** me **score më të ulët** sepse reduktojnë fuqinë kërkuese të algoritmit. Kjo nuk garanton që B gjithmonë fiton në çdo instancë të ardhshme, por **shpjegon drejtimin** e ndryshimit në këtë matje.

### Detaje sipas instancës se caktuar (mesatarja / më e mira / devijimi std)

**A_balanced_default**

| Instanca | best | mean | std |
|----------|------|------|-----|
| australia_iptv.json | 2827 | 2684.7 | 50.46 |
| canada_pw.json | 2383 | 2309.2 | 91.92 |
| china_pw.json | 2422 | 2307.5 | 97.31 |
| croatia_tv_input.json | 2099 | 2045.5 | 35.38 |
| france_iptv.json | 2595 | 2583.7 | 34.35 |
| germany_tv_input.json | 932 | 932.0 | 0.0 |
| kosovo_tv_input.json | 1629 | 1545.4 | 45.02 |
| netherlands_tv_input.json | 1708 | 1637.8 | 44.03 |
| singapore_pw.json | 3247 | 2931.3 | 180.81 |
| spain_iptv.json | 2125 | 1994.0 | 170.41 |

**B_exploration_heavy**

| Instanca | best | mean | std |
|----------|------|------|-----|
| australia_iptv.json | 3034 | 2914.4 | 55.81 |
| canada_pw.json | 2699 | 2532.4 | 152.55 |
| china_pw.json | 2413 | 2363.9 | 62.13 |
| croatia_tv_input.json | 2157 | 2099.8 | 42.97 |
| france_iptv.json | 2649 | 2605.8 | 22.77 |
| germany_tv_input.json | 932 | 932.0 | 0.0 |
| kosovo_tv_input.json | 1668 | 1625.2 | 29.39 |
| netherlands_tv_input.json | 1805 | 1744.8 | 27.87 |
| singapore_pw.json | 3402 | 3227.8 | 100.19 |
| spain_iptv.json | 2356 | 2191.3 | 66.07 |

**C_exploitation_fast**

| Instanca | best | mean | std |
|----------|------|------|-----|
| australia_iptv.json | 2676 | 2645.4 | 35.12 |
| canada_pw.json | 2383 | 2247.8 | 126.24 |
| china_pw.json | 2343 | 2253.6 | 57.35 |
| croatia_tv_input.json | 1978 | 1859.6 | 71.53 |
| france_iptv.json | 2595 | 2565.9 | 63.47 |
| germany_tv_input.json | 923 | 891.6 | 52.44 |
| kosovo_tv_input.json | 1435 | 1413.2 | 32.56 |
| netherlands_tv_input.json | 1581 | 1508.0 | 40.09 |
| singapore_pw.json | 2889 | 2752.7 | 119.24 |
| spain_iptv.json | 1721 | 1674.0 | 31.02 |

<!-- GA_LS_BENCHMARK_START -->
--- Instanca 1/1: toy.json ---
  run 01/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 02/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 04/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 05/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 06/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 08/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)
  run 10/10 | GA=380 | LS=380 | delta=+0 (+0.00% nga GA)


  --- Instanca 1/1: croatia_tv_input.json ---
  run 01/10 | GA=2157 | LS=2157 | delta=+0 (+0.00% nga GA)
  run 02/10 | GA=2079 | LS=2079 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=2021 | LS=1831 | delta=-190 (-9.40% nga GA)
  run 04/10 | GA=2021 | LS=2021 | delta=+0 (+0.00% nga GA)
  run 05/10 | GA=2021 | LS=2021 | delta=+0 (+0.00% nga GA)
  run 06/10 | GA=2021 | LS=2021 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=2099 | LS=2099 | delta=+0 (+0.00% nga GA)
  run 08/10 | GA=2138 | LS=2096 | delta=-42 (-1.96% nga GA)
  run 09/10 | GA=2021 | LS=2099 | delta=+78 (+3.86% nga GA)
  run 10/10 | GA=2021 | LS=2021 | delta=+0 (+0.00% nga GA)


  --- Instanca 1/1: germany_tv_input.json ---
  run 01/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 02/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 04/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 05/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 06/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 08/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)
  run 10/10 | GA=932 | LS=932 | delta=+0 (+0.00% nga GA)

  --- Instanca 1/1: australia_iptv.json ---
  run 01/10 | GA=2582 | LS=2582 | delta=+0 (+0.00% nga GA)
  run 02/10 | GA=2580 | LS=2580 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=2827 | LS=2827 | delta=+0 (+0.00% nga GA)
  run 04/10 | GA=2818 | LS=2827 | delta=+9 (+0.32% nga GA)
  run 05/10 | GA=2675 | LS=2675 | delta=+0 (+0.00% nga GA)
  run 06/10 | GA=2667 | LS=2654 | delta=-13 (-0.49% nga GA)
  run 07/10 | GA=2752 | LS=2752 | delta=+0 (+0.00% nga GA)
  run 08/10 | GA=2582 | LS=2582 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=2675 | LS=2675 | delta=+0 (+0.00% nga GA)
  run 10/10 | GA=2809 | LS=2811 | delta=+2 (+0.07% nga GA)

  --- Instanca 1/1: kosovo_tv_input.json ---
  run 01/10 | GA=1568 | LS=1607 | delta=+39 (+2.49% nga GA)
  run 02/10 | GA=1597 | LS=1653 | delta=+56 (+3.51% nga GA)
  run 03/10 | GA=1474 | LS=1536 | delta=+62 (+4.21% nga GA)
  run 04/10 | GA=1497 | LS=1497 | delta=+0 (+0.00% nga GA)
  run 05/10 | GA=1568 | LS=1536 | delta=-32 (-2.04% nga GA)
  run 06/10 | GA=1500 | LS=1539 | delta=+39 (+2.60% nga GA)
  run 07/10 | GA=1568 | LS=1607 | delta=+39 (+2.49% nga GA)
  run 08/10 | GA=1476 | LS=1476 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=1474 | LS=1474 | delta=+0 (+0.00% nga GA)
  run 10/10 | GA=1476 | LS=1476 | delta=+0 (+0.00% nga GA)

  --- Instanca 1/1: france_iptv.json ---
  run 01/10 | GA=2595 | LS=2595 | delta=+0 (+0.00% nga GA)
  run 02/10 | GA=2595 | LS=2595 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=2649 | LS=2649 | delta=+0 (+0.00% nga GA)
  run 04/10 | GA=2595 | LS=2595 | delta=+0 (+0.00% nga GA)
  run 05/10 | GA=2595 | LS=2595 | delta=+0 (+0.00% nga GA)
  run 06/10 | GA=2595 | LS=2595 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=2595 | LS=2595 | delta=+0 (+0.00% nga GA)
  run 08/10 | GA=2595 | LS=2595 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=2595 | LS=2432 | delta=-163 (-6.28% nga GA)
  run 10/10 | GA=2595 | LS=2436 | delta=-159 (-6.13% nga GA)

  --- Instanca 1/1: netherlands_tv_input.json ---
  run 01/10 | GA=1639 | LS=1608 | delta=-31 (-1.89% nga GA)
  run 02/10 | GA=1589 | LS=1590 | delta=+1 (+0.06% nga GA)
  run 03/10 | GA=1639 | LS=1589 | delta=-50 (-3.05% nga GA)
  run 04/10 | GA=1656 | LS=1738 | delta=+82 (+4.95% nga GA)
  run 05/10 | GA=1688 | LS=1621 | delta=-67 (-3.97% nga GA)
  run 06/10 | GA=1726 | LS=1726 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=1681 | LS=1689 | delta=+8 (+0.48% nga GA)
  run 08/10 | GA=1590 | LS=1693 | delta=+103 (+6.48% nga GA)
  run 09/10 | GA=1666 | LS=1612 | delta=-54 (-3.24% nga GA)
  run 10/10 | GA=1639 | LS=1639 | delta=+0 (+0.00% nga GA)

  --- Instanca 1/1: spain_iptv.json ---
  run 01/10 | GA=2011 | LS=2132 | delta=+121 (+6.02% nga GA)
  run 02/10 | GA=1833 | LS=1669 | delta=-164 (-8.95% nga GA)
  run 03/10 | GA=2134 | LS=2134 | delta=+0 (+0.00% nga GA)
  run 04/10 | GA=1743 | LS=1743 | delta=+0 (+0.00% nga GA)
  run 05/10 | GA=1767 | LS=1771 | delta=+4 (+0.23% nga GA)
  run 06/10 | GA=1838 | LS=1838 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=1721 | LS=1721 | delta=+0 (+0.00% nga GA)
  run 08/10 | GA=1830 | LS=1830 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=1750 | LS=1745 | delta=-5 (-0.29% nga GA)
  run 10/10 | GA=1831 | LS=1833 | delta=+2 (+0.11% nga GA)

  --- Instanca 1/1: uk_tv_input.json ---
  run 01/10 | GA=1930 | LS=1973 | delta=+43 (+2.23% nga GA)
  run 02/10 | GA=1915 | LS=1928 | delta=+13 (+0.68% nga GA)
  run 03/10 | GA=1846 | LS=1850 | delta=+4 (+0.22% nga GA)
  run 04/10 | GA=1913 | LS=1917 | delta=+4 (+0.21% nga GA)
  run 05/10 | GA=1882 | LS=1924 | delta=+42 (+2.23% nga GA)
  run 06/10 | GA=1934 | LS=1940 | delta=+6 (+0.31% nga GA)
  run 07/10 | GA=1844 | LS=1852 | delta=+8 (+0.43% nga GA)
  run 08/10 | GA=1870 | LS=1870 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=1795 | LS=1795 | delta=+0 (+0.00% nga GA)
  run 10/10 | GA=1817 | LS=1882 | delta=+65 (+3.58% nga GA)
  
  --- Instanca 1/1: singapore_pw.json ---
  run 01/10 | GA=3173 | LS=3205 | delta=+32 (+1.01% nga GA)
  run 02/10 | GA=3070 | LS=3355 | delta=+285 (+9.28% nga GA)
  run 03/10 | GA=3219 | LS=2958 | delta=-261 (-8.11% nga GA)
  run 04/10 | GA=3063 | LS=3153 | delta=+90 (+2.94% nga GA)
  run 05/10 | GA=3031 | LS=3372 | delta=+341 (+11.25% nga GA)
  run 01/10 | GA=3173 | LS=3205 | delta=+32 (+1.01% nga GA)
  run 02/10 | GA=3070 | LS=3355 | delta=+285 (+9.28% nga GA)
  run 06/10 | GA=3160 | LS=3277 | delta=+117 (+3.70% nga GA)       
  run 07/10 | GA=3188 | LS=3206 | delta=+18 (+0.56% nga GA)        
  run 08/10 | GA=3321 | LS=3489 | delta=+168 (+5.06% nga GA)       
  run 09/10 | GA=3349 | LS=3392 | delta=+43 (+1.28% nga GA)        
  run 10/10 | GA=3207 | LS=3183 | delta=-24 (-0.75% nga GA) 

--- Instanca 1/1: canada_pw.json ---
  run 01/10 | GA=2383 | LS=2383 | delta=+0 (+0.00% nga GA)
  run 02/10 | GA=2382 | LS=2382 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=2302 | LS=1957 | delta=-345 (-14.99% nga GA)
   run 04/10 | GA=2383 | LS=2375 | delta=-8 (-0.34% nga GA)
  run 05/10 | GA=2383 | LS=2381 | delta=-2 (-0.08% nga GA)
  run 06/10 | GA=2383 | LS=2383 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=2373 | LS=2374 | delta=+1 (+0.04% nga GA)
  run 08/10 | GA=2383 | LS=2383 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=2383 | LS=2375 | delta=-8 (-0.34% nga GA)
  run 10/10 | GA=2412 | LS=2376 | delta=-36 (-1.49% nga GA)


  --- Instanca 1/1: uk_iptv.json ---
  run 01/10 | GA=2500 | LS=2500 | delta=+0 (+0.00% nga GA)
  run 02/10 | GA=2500 | LS=2500 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=2500 | LS=2499 | delta=-1 (-0.04% nga GA)
  run 04/10 | GA=2630 | LS=2630 | delta=+0 (+0.00% nga GA)
  run 05/10 | GA=2486 | LS=2486 | delta=+0 (+0.00% nga GA)
  run 06/10 | GA=2500 | LS=2500 | delta=+0 (+0.00% nga GA)
  run 07/10 | GA=2521 | LS=2523 | delta=+2 (+0.08% nga GA)
  run 08/10 | GA=2630 | LS=2630 | delta=+0 (+0.00% nga GA)
  run 09/10 | GA=2630 | LS=2623 | delta=-7 (-0.27% nga GA)
  run 10/10 | GA=2500 | LS=2500 | delta=+0 (+0.00% nga GA)

--- Instanca 1/1: china_pw.json ---
  run 01/10 | GA=2399 | LS=2410 | delta=+11 (+0.46% nga GA)
  run 02/10 | GA=2418 | LS=2418 | delta=+0 (+0.00% nga GA)
  run 03/10 | GA=2408 | LS=2112 | delta=-296 (-12.29% nga GA)       
  run 04/10 | GA=2347 | LS=2218 | delta=-129 (-5.50% nga GA)        
  run 05/10 | GA=2400 | LS=2407 | delta=+7 (+0.29% nga GA)
  run 06/10 | GA=2414 | LS=2420 | delta=+6 (+0.25% nga GA)
  run 07/10 | GA=2419 | LS=2229 | delta=-190 (-7.85% nga GA)        
  run 08/10 | GA=2410 | LS=2340 | delta=-70 (-2.90% nga GA)
  run 09/10 | GA=2405 | LS=2404 | delta=-1 (-0.04% nga GA)
  run 10/10 | GA=2384 | LS=2441 | delta=+57 (+2.39% nga GA)

  --- Instanca 1/1: usa_tv_input.json ---
  run 01/10 | GA=2691 | LS=2455 | delta=-236 (-8.77% nga GA)        
  run 02/10 | GA=2838 | LS=2470 | delta=-368 (-12.97% nga GA)       
  run 03/10 | GA=2613 | LS=2661 | delta=+48 (+1.84% nga GA)
  run 04/10 | GA=2711 | LS=2379 | delta=-332 (-12.25% nga GA)

  --- Instanca 1/1: us_iptv.json ---
  run 01/10 | GA=1632 | LS=1632 | delta=+0 (+0.00% nga GA)

  --- Instanca 1/1: youtube_gold.json ---
  run 01/10 | GA=14449 | LS=15577 | delta=+1128 (+7.81% nga GA)     
  run 02/10 | GA=14454 | LS=15094 | delta=+640 (+4.43% nga GA)      
  run 03/10 | GA=14901 | LS=15501 | delta=+600 (+4.03% nga GA)      
  run 04/10 | GA=14062 | LS=15282 | delta=+1220 (+8.68% nga GA)     
  run 05/10 | GA=14223 | LS=15139 | delta=+916 (+6.44% nga GA)      
  run 06/10 | GA=14197 | LS=15250 | delta=+1053 (+7.42% nga GA)     
  run 07/10 | GA=14128 | LS=14318 | delta=+190 (+1.34% nga GA)      
  run 08/10 | GA=14367 | LS=16084 | delta=+1717 (+11.95% nga GA)
  run 09/10 | GA=13653 | LS=14187 | delta=+534 (+3.91% nga GA)
  run 10/10 | GA=14049 | LS=14413 | delta=+364 (+2.59% nga GA)

  --- Instanca 1/1: youtube_premium.json ---
  run 01/10 | GA=23745 | LS=25708 | delta=+1963 (+8.27% nga GA)     
  run 02/10 | GA=24388 | LS=24227 | delta=-161 (-0.66% nga GA)      
  run 03/10 | GA=23948 | LS=24606 | delta=+658 (+2.75% nga GA)
  run 04/10 | GA=24241 | LS=22872 | delta=-1369 (-5.65% nga GA)
  run 05/10 | GA=24784 | LS=26281 | delta=+1497 (+6.04% nga GA)
  run 06/10 | GA=24630 | LS=25883 | delta=+1253 (+5.09% nga GA)
  run 07/10 | GA=23927 | LS=24731 | delta=+804 (+3.36% nga GA)
  run 08/10 | GA=24352 | LS=25625 | delta=+1273 (+5.23% nga GA)
  run 09/10 | GA=24784 | LS=26281 | delta=+1497 (+6.04% nga GA)
  run 10/10 | GA=24241 | LS=22872 | delta=-1369 (-5.65% nga GA)
<!-- GA_LS_BENCHMARK_END -->

---

