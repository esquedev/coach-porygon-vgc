# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Speed Duel Scenarios Generator & CSV Persistence
Generates 50 deterministic Level 50 Speed Duel flashcards for reflex training.
Conditions describe battle context WITHOUT spoiling speed numbers prior to guessing.
Reflects the 5-7s Speed Reflex Benchmark: in tournament play, identifying the speed
order must happen in under 7 seconds so the remaining ~38s of the 45s turn can be
dedicated to targeting, prediction, and Minimax lookahead.
Writes:
- `engine/speed_duels_data.py`
- `data/Speed_Duel_Scenarios.csv`
- `tests/data/Speed_Duel_Scenarios.csv`
"""

import csv
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine"))
from validate_roster import load_legal_items

legal_items = load_legal_items()

SPEED_DUELS = [
  {
    "id": "SD-01",
    "title": "Base Speed: Garchomp vs Charizard-Mega-Y",
    "category": "Base Speed",
    "monA": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 169 },
    "monB": { "name": "Charizard-Mega-Y", "species": "Charizard-Mega-Y", "nature": "Timid", "item": "Charizardite Y", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 167 },
    "winner": "A",
    "winnerName": "Garchomp",
    "speedDiff": 2,
    "explanation_es": "Garchomp Jolly con 32 SP alcanza 169 Spe a Nivel 50, superando por 2 puntos a Charizard-Mega-Y Timid con 32 SP (167 Spe). En torneo debes reconocer este benchmark en <5s para planificar tus ataques.",
    "explanation_en": "Jolly Garchomp with 32 SP reaches 169 Spe at Level 50, outspeeding Timid Charizard-Mega-Y (167 Spe) by 2 points. Recognize this 2-point edge in <5s to allocate turn time."
  },
  {
    "id": "SD-02",
    "title": "Mega Instantánea: Lucario-Mega vs Garchomp",
    "category": "Mega Evolution",
    "monA": { "name": "Lucario-Mega", "species": "Lucario-Mega", "nature": "Timid", "item": "Lucarionite", "condition": "Recálculo Instantáneo post-Mega", "calculatedSpe": 180 },
    "monB": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 169 },
    "winner": "A",
    "winnerName": "Lucario-Mega",
    "speedDiff": 11,
    "explanation_es": "En Regulation M-C la Mega Evolución actualiza la velocidad de inmediato en el Activation Phase. Lucario-Mega (112 Base) llega a 180 Spe y supera a Garchomp (169 Spe) por 11 puntos.",
    "explanation_en": "In Regulation M-C, Mega Evolution recalculates speed instantly during the Activation Phase. Mega Lucario (112 Base) reaches 180 Spe and outspeeds Garchomp (169 Spe) by 11 points."
  },
  {
    "id": "SD-03",
    "title": "Swift Swim vs Unburden: Basculegion en Lluvia vs Sneasler Unburden",
    "category": "Clima & Habilidad",
    "monA": { "name": "Basculegion-M", "species": "Basculegion-M", "nature": "Modest", "item": "Life Orb", "condition": "Habilidad Swift Swim bajo Lluvia activa", "calculatedSpe": 260 },
    "monB": { "name": "Sneasler", "species": "Sneasler", "nature": "Jolly", "item": "Electric Seed", "condition": "Habilidad Unburden activada tras Electric Seed", "calculatedSpe": 378 },
    "winner": "B",
    "winnerName": "Sneasler",
    "speedDiff": 118,
    "explanation_es": "Sneasler Jolly con Unburden activado alcanza 378 Spe masivos, superando por 118 puntos al Basculegion Modest en lluvia (260 Spe). Sneasler ataca primero.",
    "explanation_en": "Jolly Sneasler with Unburden active reaches a massive 378 Spe, outspeeding Modest Basculegion in Rain (260 Spe) by 118 points. Sneasler moves first."
  },
  {
    "id": "SD-04",
    "title": "Prioridades Relativas: Fake Out (+3) vs Extreme Speed (+2)",
    "category": "Prioridad",
    "monA": { "name": "Incineroar", "species": "Incineroar", "nature": "Careful", "item": "Sitrus Berry", "condition": "Usa Fake Out (Prioridad +3)", "calculatedSpe": 999 },
    "monB": { "name": "Dragonite", "species": "Dragonite", "nature": "Adamant", "item": "Lum Berry", "condition": "Usa Extreme Speed (Prioridad +2)", "calculatedSpe": 888 },
    "winner": "A",
    "winnerName": "Incineroar",
    "speedDiff": 1,
    "explanation_es": "Fake Out opera en el bracket de +3 Prioridad, superando siempre a Extreme Speed que opera en el bracket de +2 Prioridad, sin importar la estadística de velocidad base.",
    "explanation_en": "Fake Out operates at +3 Priority, strictly beating Extreme Speed at +2 Priority regardless of underlying base speed stats."
  },
  {
    "id": "SD-05",
    "title": "Mismo Bracket de Prioridad (+1): Grassy Glide vs Sucker Punch",
    "category": "Prioridad",
    "monA": { "name": "Rillaboom", "species": "Rillaboom", "nature": "Adamant", "item": "Miracle Seed", "condition": "Grassy Glide en Grassy Terrain (+1 Prioridad)", "calculatedSpe": 117 },
    "monB": { "name": "Kingambit", "species": "Kingambit", "nature": "Adamant", "item": "Black Glasses", "condition": "Sucker Punch (+1 Prioridad)", "calculatedSpe": 70 },
    "winner": "A",
    "winnerName": "Rillaboom",
    "speedDiff": 47,
    "explanation_es": "Cuando dos movimientos comparten el mismo bracket de prioridad (+1), el desempate lo dicta la estadística de Velocidad Nivel 50: Rillaboom (117 Spe) supera a Kingambit (70 Spe).",
    "explanation_en": "When moves share the same priority bracket (+1), the tie is broken by Level 50 Speed: Rillaboom (117 Spe) outspeeds Kingambit (70 Spe)."
  },
  {
    "id": "SD-06",
    "title": "Choice Scarf: Archaludon Scarf vs Gengar-Mega",
    "category": "Choice Scarf",
    "monA": { "name": "Archaludon", "species": "Archaludon", "nature": "Timid", "item": "Choice Scarf", "condition": "Equipado con Choice Scarf (x1.5 Spe)", "calculatedSpe": 205 },
    "monB": { "name": "Gengar-Mega", "species": "Gengar-Mega", "nature": "Timid", "item": "Gengarite", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 200 },
    "winner": "A",
    "winnerName": "Archaludon",
    "speedDiff": 5,
    "explanation_es": "Archaludon con Choice Scarf multiplica sus 137 Spe por 1.5 resultando en 205 Spe efectivos, superando por 5 puntos al Gengar-Mega Timid a máxima velocidad (200 Spe).",
    "explanation_en": "Choice Scarf Archaludon multiplies its 137 Spe by 1.5 to reach 205 effective Spe, edging out Timid Mega Gengar (200 Spe) by 5 points."
  },
  {
    "id": "SD-07",
    "title": "Inversión de Trick Room: Torkoal vs Farigiraf",
    "category": "Trick Room",
    "monA": { "name": "Torkoal", "species": "Torkoal", "nature": "Quiet", "item": "Heat Rock", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 22 },
    "monB": { "name": "Farigiraf", "species": "Farigiraf", "nature": "Quiet", "item": "Mental Herb", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 58 },
    "winner": "A",
    "winnerName": "Torkoal",
    "speedDiff": 36,
    "explanation_es": "Bajo Trick Room (Espacio Raro), el orden de velocidad se invierte completamente: el Pokémon más lento se mueve primero. Torkoal (22 Spe) se mueve antes que Farigiraf (58 Spe).",
    "explanation_en": "Under Trick Room, turn order is strictly inverted: the slowest moves first. Torkoal (22 Spe) moves before Farigiraf (58 Spe)."
  },
  {
    "id": "SD-08",
    "title": "Caída de Velocidad (-1 Spe): Primarina vs Armarouge",
    "category": "Stat Stages",
    "monA": { "name": "Primarina", "species": "Primarina", "nature": "Modest", "item": "Mystic Water", "condition": "Caída de -1 Spe por Electroweb", "calculatedSpe": 74 },
    "monB": { "name": "Armarouge", "species": "Armarouge", "nature": "Modest", "item": "Life Orb", "condition": "Velocidad neutral sin modificadores", "calculatedSpe": 95 },
    "winner": "B",
    "winnerName": "Armarouge",
    "speedDiff": 21,
    "explanation_es": "Tras recibir una caída de -1 Spe por Electroweb o Icy Wind, la velocidad de Primarina se reduce al 66% (74 Spe), permitiendo a Armarouge (95 Spe) moverse primero.",
    "explanation_en": "After a -1 Spe drop from Electroweb, Primarina drops to 74 Spe, allowing Armarouge (95 Spe) to attack first."
  },
  {
    "id": "SD-09",
    "title": "Speed Tier Máximo: Sneasler vs Gengar-Mega",
    "category": "Base Speed",
    "monA": { "name": "Sneasler", "species": "Sneasler", "nature": "Jolly", "item": "Focus Sash", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 189 },
    "monB": { "name": "Gengar-Mega", "species": "Gengar-Mega", "nature": "Timid", "item": "Gengarite", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 200 },
    "winner": "B",
    "winnerName": "Gengar-Mega",
    "speedDiff": 11,
    "explanation_es": "Gengar-Mega posee Base 130 frente a la Base 120 de Sneasler. A 32 SP con naturaleza favorable, Gengar-Mega (200 Spe) supera a Sneasler (189 Spe) por 11 puntos.",
    "explanation_en": "Mega Gengar has Base 130 Spe versus Sneasler's Base 120. Timid Mega Gengar (200 Spe) cleanly outspeeds Jolly Sneasler (189 Spe) by 11 points."
  },
  {
    "id": "SD-10",
    "title": "Tailwind vs Clima: Charizard-Mega-Y en Tailwind vs Basculegion en Lluvia",
    "category": "Clima & Tailwind",
    "monA": { "name": "Charizard-Mega-Y", "species": "Charizard-Mega-Y", "nature": "Timid", "item": "Charizardite Y", "condition": "Bajo Viento Afín (Tailwind x2 Spe)", "calculatedSpe": 334 },
    "monB": { "name": "Basculegion-M", "species": "Basculegion-M", "nature": "Modest", "item": "Life Orb", "condition": "Bajo Lluvia activa (Swift Swim x2 Spe)", "calculatedSpe": 260 },
    "winner": "A",
    "winnerName": "Charizard-Mega-Y",
    "speedDiff": 74,
    "explanation_es": "Charizard-Mega-Y bajo Tailwind duplica sus 167 Spe alcanzando 334 Spe, superando con creces los 260 Spe de Basculegion bajo lluvia. Charizard ataca primero.",
    "explanation_en": "Mega Charizard Y under Tailwind hits 334 Spe, comfortably outpacing Rain Swift Swim Basculegion (260 Spe) by 74 points."
  },
  {
    "id": "SD-11",
    "title": "Choice Scarf Dragonite vs Lucario-Mega",
    "category": "Choice Scarf",
    "monA": { "name": "Dragonite", "species": "Dragonite", "nature": "Jolly", "item": "Choice Scarf", "condition": "Equipado con Choice Scarf (x1.5 Spe)", "calculatedSpe": 217 },
    "monB": { "name": "Lucario-Mega", "species": "Lucario-Mega", "nature": "Timid", "item": "Lucarionite", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 180 },
    "winner": "A",
    "winnerName": "Dragonite",
    "speedDiff": 37,
    "explanation_es": "Dragonite con Choice Scarf alcanza 217 Spe a Nivel 50, superando los 180 Spe de Lucario-Mega y pudiendo noquearlo antes de que ataque.",
    "explanation_en": "Choice Scarf Dragonite hits 217 Spe at Level 50, outpacing Timid Mega Lucario (180 Spe) by 37 points."
  },
  {
    "id": "SD-12",
    "title": "Raichu-Mega-X vs Garchomp",
    "category": "Mega Evolution",
    "monA": { "name": "Raichu-Mega-X", "species": "Raichu-Mega-X", "nature": "Timid", "item": "Raichunite X", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 178 },
    "monB": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 169 },
    "winner": "A",
    "winnerName": "Raichu-Mega-X",
    "speedDiff": 9,
    "explanation_es": "Raichu-Mega-X posee Base 110 llegando a 178 Spe Nivel 50, lo que le permite superar a Garchomp Jolly (169 Spe) por 9 puntos.",
    "explanation_en": "Mega Raichu X features Base 110 Spe reaching 178 Spe at Level 50, outspeeding Jolly Garchomp (169 Spe) by 9 points."
  },
  {
    "id": "SD-13",
    "title": "Speed Tie Oficial: Incineroar vs Primarina",
    "category": "Speed Tie",
    "monA": { "name": "Incineroar", "species": "Incineroar", "nature": "Careful", "item": "Sitrus Berry", "condition": "Sin inversión en velocidad (0 SP Spe)", "calculatedSpe": 80 },
    "monB": { "name": "Primarina", "species": "Primarina", "nature": "Modest", "item": "Mystic Water", "condition": "Sin inversión en velocidad (0 SP Spe)", "calculatedSpe": 80 },
    "winner": "TIE",
    "winnerName": "Empate (Speed Tie 50/50)",
    "speedDiff": 0,
    "explanation_es": "Ambos comparten Base 60 y 80 Spe exactos a Nivel 50 con 0 SP invertidos. El motor de batalla lanza una moneda 50/50 en cada turno para determinar quién actúa primero.",
    "explanation_en": "Both share Base 60 and exact 80 Spe at Level 50 with 0 Speed SP. The engine executes a 50/50 roll each turn to decide who moves first."
  },
  {
    "id": "SD-14",
    "title": "Gale Wings (+1) vs Prankster (+1): Talonflame vs Whimsicott",
    "category": "Prioridad",
    "monA": { "name": "Talonflame", "species": "Talonflame", "nature": "Jolly", "item": "Mental Herb", "condition": "Gale Wings a 100% HP (Tailwind +1 Prio)", "calculatedSpe": 195 },
    "monB": { "name": "Whimsicott", "species": "Whimsicott", "nature": "Timid", "item": "Mental Herb", "condition": "Prankster (Tailwind +1 Prio)", "calculatedSpe": 184 },
    "winner": "A",
    "winnerName": "Talonflame",
    "speedDiff": 11,
    "explanation_es": "Ambos movimientos tienen +1 de prioridad. Al empatar en prioridad, el desempate por velocidad favorece a Talonflame (195 Spe) sobre Whimsicott (184 Spe).",
    "explanation_en": "Both moves sit at +1 priority. The speed tiebreaker awards turn order to Talonflame (195 Spe) over Whimsicott (184 Spe)."
  },
  {
    "id": "SD-15",
    "title": "Boost de Velocidad (+1): Annihilape +1 Spe vs Gengar-Mega",
    "category": "Stat Stages",
    "monA": { "name": "Annihilape", "species": "Annihilape", "nature": "Adamant", "item": "Leftovers", "condition": "Boost de +1 Spe activo", "calculatedSpe": 213 },
    "monB": { "name": "Gengar-Mega", "species": "Gengar-Mega", "nature": "Timid", "item": "Gengarite", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 200 },
    "winner": "A",
    "winnerName": "Annihilape",
    "speedDiff": 13,
    "explanation_es": "Con +1 en Velocidad, Annihilape escala a 213 Spe efectivos, superando a Gengar-Mega (200 Spe) por 13 puntos y pudiendo noquearlo con Rage Fist.",
    "explanation_en": "At +1 Speed, Annihilape climbs to 213 Spe, cleanly outpacing Mega Gengar (200 Spe) by 13 points."
  },
  {
    "id": "SD-16",
    "title": "Weak Armor (+2 Spe): Armarouge vs Sneasler",
    "category": "Stat Stages",
    "monA": { "name": "Armarouge", "species": "Armarouge", "nature": "Modest", "item": "Life Orb", "condition": "Boost de +2 Spe tras activar Weak Armor", "calculatedSpe": 254 },
    "monB": { "name": "Sneasler", "species": "Sneasler", "nature": "Jolly", "item": "Focus Sash", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 189 },
    "winner": "A",
    "winnerName": "Armarouge",
    "speedDiff": 65,
    "explanation_es": "La activación de Weak Armor otorga +2 en Velocidad (+100%), llevando a Armarouge a 254 Spe y superando fácilmente a Sneasler (189 Spe).",
    "explanation_en": "Activating Weak Armor grants +2 Speed (+100%), taking Armarouge to 254 Spe to easily outspeed Sneasler (189 Spe)."
  },
  {
    "id": "SD-17",
    "title": "Maushold vs Charizard-Mega-Y",
    "category": "Base Speed",
    "monA": { "name": "Maushold", "species": "Maushold", "nature": "Jolly", "item": "Focus Sash", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 179 },
    "monB": { "name": "Charizard-Mega-Y", "species": "Charizard-Mega-Y", "nature": "Timid", "item": "Charizardite Y", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 167 },
    "winner": "A",
    "winnerName": "Maushold",
    "speedDiff": 12,
    "explanation_es": "Maushold (Base 111) alcanza 179 Spe a Nivel 50, superando a Charizard-Mega-Y (Base 100, 167 Spe) por 12 puntos y pudiendo usar Super Fang antes.",
    "explanation_en": "Maushold (Base 111) hits 179 Spe at Level 50, outspeeding Mega Charizard Y (Base 100, 167 Spe) by 12 points."
  },
  {
    "id": "SD-18",
    "title": "Tailwind Garchomp vs Dragapult",
    "category": "Clima & Tailwind",
    "monA": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Bajo Viento Afín (Tailwind x2 Spe)", "calculatedSpe": 338 },
    "monB": { "name": "Dragapult", "species": "Dragapult", "nature": "Timid", "item": "Twisted Spoon", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 213 },
    "winner": "A",
    "winnerName": "Garchomp",
    "speedDiff": 125,
    "explanation_es": "Garchomp bajo Tailwind duplica su velocidad hasta 338 Spe, dejando atrás al Pokémon no-Mega más rápido del formato (Dragapult, 213 Spe).",
    "explanation_en": "Tailwind Garchomp doubles to 338 Spe, completely outspeeding Dragapult (213 Spe) by 125 points."
  },
  {
    "id": "SD-19",
    "title": "Trick Room: Tyranitar vs Kingambit",
    "category": "Trick Room",
    "monA": { "name": "Tyranitar", "species": "Tyranitar", "nature": "Brave", "item": "Rocky Helmet", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 63 },
    "monB": { "name": "Kingambit", "species": "Kingambit", "nature": "Brave", "item": "Black Glasses", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 49 },
    "winner": "B",
    "winnerName": "Kingambit",
    "speedDiff": 14,
    "explanation_es": "En Trick Room el más lento ataca primero. Kingambit (Base 50 con 49 Spe) es más lento que Tyranitar (Base 61 con 63 Spe), por lo que Kingambit gana el turno.",
    "explanation_en": "Under Trick Room, the slower Pokemon moves first. Kingambit (49 Spe) is slower than Tyranitar (63 Spe), granting Kingambit the first move."
  },
  {
    "id": "SD-20",
    "title": "Clima vs Scarf: Basculegion en Lluvia vs Dragapult Scarf",
    "category": "Clima & Tailwind",
    "monA": { "name": "Basculegion-M", "species": "Basculegion-M", "nature": "Modest", "item": "Life Orb", "condition": "Habilidad Swift Swim bajo Lluvia activa", "calculatedSpe": 260 },
    "monB": { "name": "Dragapult", "species": "Dragapult", "nature": "Timid", "item": "Choice Scarf", "condition": "Equipado con Choice Scarf (x1.5 Spe)", "calculatedSpe": 319 },
    "winner": "B",
    "winnerName": "Dragapult",
    "speedDiff": 59,
    "explanation_es": "Dragapult Choice Scarf multiplica sus 213 Spe por 1.5 llegando a 319 Spe, superando incluso a Basculegion bajo lluvia (260 Spe). Dragapult ataca primero.",
    "explanation_en": "Choice Scarf Dragapult hits 319 Spe, easily outpacing Swift Swim Basculegion (260 Spe) by 59 points."
  },
  {
    "id": "SD-21",
    "title": "Mega Lucario vs Talonflame (Sin Prioridad)",
    "category": "Base Speed",
    "monA": { "name": "Lucario-Mega", "species": "Lucario-Mega", "nature": "Timid", "item": "Lucarionite", "condition": "Recálculo Instantáneo post-Mega", "calculatedSpe": 180 },
    "monB": { "name": "Talonflame", "species": "Talonflame", "nature": "Jolly", "item": "Mental Herb", "condition": "Movimiento estándar sin prioridad", "calculatedSpe": 195 },
    "winner": "B",
    "winnerName": "Talonflame",
    "speedDiff": 15,
    "explanation_es": "Sin movimientos de prioridad, la velocidad pura de Talonflame (Base 126, 195 Spe) supera a Lucario-Mega (Base 112, 180 Spe) por 15 puntos.",
    "explanation_en": "With standard non-priority attacks, Talonflame's natural 195 Spe outspeeds Mega Lucario's 180 Spe by 15 points."
  },
  {
    "id": "SD-22",
    "title": "Duelo de Bulk: Rillaboom vs Incineroar",
    "category": "Base Speed",
    "monA": { "name": "Rillaboom", "species": "Rillaboom", "nature": "Adamant", "item": "Miracle Seed", "condition": "Inversión bulky moderada (12 SP Spe)", "calculatedSpe": 117 },
    "monB": { "name": "Incineroar", "species": "Incineroar", "nature": "Careful", "item": "Sitrus Berry", "condition": "Inversión bulky baja (4 SP Spe)", "calculatedSpe": 85 },
    "winner": "A",
    "winnerName": "Rillaboom",
    "speedDiff": 32,
    "explanation_es": "Rillaboom (Base 85, 117 Spe) supera naturalmente a Incineroar (Base 60, 85 Spe), permitiendo a Rillaboom usar Knock Off antes que Incineroar ataque.",
    "explanation_en": "Rillaboom (Base 85, 117 Spe) naturally outspeeds bulky Incineroar (Base 60, 85 Spe) by 32 points."
  },
  {
    "id": "SD-23",
    "title": "Fake Out (+3) vs Prankster (+1): Whimsicott vs Rillaboom",
    "category": "Prioridad",
    "monA": { "name": "Whimsicott", "species": "Whimsicott", "nature": "Timid", "item": "Mental Herb", "condition": "Tailwind con Prankster (+1 Prioridad)", "calculatedSpe": 184 },
    "monB": { "name": "Rillaboom", "species": "Rillaboom", "nature": "Adamant", "item": "Rocky Helmet", "condition": "Ejecuta Fake Out (Prioridad +3)", "calculatedSpe": 999 },
    "winner": "B",
    "winnerName": "Rillaboom",
    "speedDiff": 1,
    "explanation_es": "Fake Out opera en +3 de prioridad, impactando y haciendo retroceder a Whimsicott antes de que pueda activar su Tailwind de +1 prioridad de Prankster.",
    "explanation_en": "Fake Out acts at +3 priority, flinching Whimsicott before its +1 Prankster Tailwind can resolve."
  },
  {
    "id": "SD-24",
    "title": "Duelo Lento: Pelipper vs Torkoal",
    "category": "Base Speed",
    "monA": { "name": "Pelipper", "species": "Pelipper", "nature": "Bold", "item": "Damp Rock", "condition": "Sin inversión en velocidad (0 SP Spe)", "calculatedSpe": 85 },
    "monB": { "name": "Torkoal", "species": "Torkoal", "nature": "Quiet", "item": "Heat Rock", "condition": "Sin inversión en velocidad (0 SP Spe)", "calculatedSpe": 40 },
    "winner": "A",
    "winnerName": "Pelipper",
    "speedDiff": 45,
    "explanation_es": "Pelipper (Base 65, 85 Spe) supera a Torkoal (Base 20, 40 Spe). En clima normal, Pelipper ataca primero con Weather Ball de agua.",
    "explanation_en": "Pelipper (Base 65, 85 Spe) naturally outspeeds Torkoal (Base 20, 40 Spe) by 45 points."
  },
  {
    "id": "SD-25",
    "title": "Tailwind Garchomp vs Unburden Sneasler",
    "category": "Clima & Tailwind",
    "monA": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Bajo Viento Afín (Tailwind x2 Spe)", "calculatedSpe": 338 },
    "monB": { "name": "Sneasler", "species": "Sneasler", "nature": "Jolly", "item": "Electric Seed", "condition": "Habilidad Unburden activada tras Electric Seed", "calculatedSpe": 378 },
    "winner": "B",
    "winnerName": "Sneasler",
    "speedDiff": 40,
    "explanation_es": "Sneasler con Unburden alcanza 378 Spe masivos (Base 120 x 2), superando incluso a Garchomp bajo Tailwind (Base 102 x 2 = 338 Spe) por 40 puntos.",
    "explanation_en": "Unburden Sneasler hits 378 Spe, outspeeding even Tailwind Garchomp (338 Spe) by 40 points."
  },
  {
    "id": "SD-26",
    "title": "Speed Tier Máximo: Meowscarada vs Gengar-Mega",
    "category": "Base Speed",
    "monA": { "name": "Meowscarada", "species": "Meowscarada", "nature": "Jolly", "item": "Focus Sash", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 192 },
    "monB": { "name": "Gengar-Mega", "species": "Gengar-Mega", "nature": "Timid", "item": "Gengarite", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 200 },
    "winner": "B",
    "winnerName": "Gengar-Mega",
    "speedDiff": 8,
    "explanation_es": "Gengar-Mega posee Base 130 alcanzando 200 Spe Nivel 50, superando los 192 Spe de Meowscarada (Base 123) por 8 puntos. Gengar-Mega ataca primero con Sludge Bomb.",
    "explanation_en": "Mega Gengar has Base 130 Spe reaching 200 Spe at Level 50, outpacing Jolly Meowscarada (192 Spe, Base 123) by 8 points."
  },
  {
    "id": "SD-27",
    "title": "Mega Instantánea: Salamence-Mega vs Whimsicott",
    "category": "Mega Evolution",
    "monA": { "name": "Salamence-Mega", "species": "Salamence-Mega", "nature": "Timid", "item": "Salamencite", "condition": "Recálculo Instantáneo post-Mega", "calculatedSpe": 189 },
    "monB": { "name": "Whimsicott", "species": "Whimsicott", "nature": "Timid", "item": "Mental Herb", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 184 },
    "winner": "A",
    "winnerName": "Salamence-Mega",
    "speedDiff": 5,
    "explanation_es": "En forma base Salamence tiene Base 100 (167 Spe) y sería más lento, pero la Mega Evolución instantánea lo eleva a Base 120 (189 Spe), superando a Whimsicott (184 Spe) por 5 puntos.",
    "explanation_en": "Pre-Mega Salamence has Base 100 (167 Spe), but instantaneous Mega Evolution scales it to Base 120 (189 Spe), cleanly outspeeding Whimsicott (184 Spe) by 5 points."
  },
  {
    "id": "SD-28",
    "title": "Choice Scarf Annihilape vs Dragapult",
    "category": "Choice Scarf",
    "monA": { "name": "Annihilape", "species": "Annihilape", "nature": "Jolly", "item": "Choice Scarf", "condition": "Equipado con Choice Scarf (x1.5 Spe)", "calculatedSpe": 234 },
    "monB": { "name": "Dragapult", "species": "Dragapult", "nature": "Timid", "item": "Life Orb", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 213 },
    "winner": "A",
    "winnerName": "Annihilape",
    "speedDiff": 21,
    "explanation_es": "Annihilape Jolly con Choice Scarf escala de 156 Spe a 234 Spe efectivos, superando por 21 puntos al Dragapult natural a máxima velocidad (213 Spe).",
    "explanation_en": "Jolly Choice Scarf Annihilape multiplies 156 Spe to reach 234 Spe, comfortably outpacing maximum natural Dragapult (213 Spe) by 21 points."
  },
  {
    "id": "SD-29",
    "title": "Clima: Venusaur en Sol vs Dragapult",
    "category": "Clima & Tailwind",
    "monA": { "name": "Venusaur", "species": "Venusaur", "nature": "Modest", "item": "Life Orb", "condition": "Habilidad Chlorophyll bajo Sol activo (x2 Spe)", "calculatedSpe": 264 },
    "monB": { "name": "Dragapult", "species": "Dragapult", "nature": "Timid", "item": "Focus Sash", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 213 },
    "winner": "A",
    "winnerName": "Venusaur",
    "speedDiff": 51,
    "explanation_es": "Bajo Sol activo, la habilidad Chlorophyll duplica los 132 Spe de Venusaur Modest hasta 264 Spe, superando fácilmente a Dragapult (213 Spe) por 51 puntos.",
    "explanation_en": "Under Sun, Chlorophyll doubles Modest Venusaur from 132 to 264 Spe, easily outspeeding Dragapult (213 Spe) by 51 points."
  },
  {
    "id": "SD-30",
    "title": "Brackets de Prioridad: Extreme Speed (+2) vs Sucker Punch (+1)",
    "category": "Prioridad",
    "monA": { "name": "Dragonite", "species": "Dragonite", "nature": "Adamant", "item": "Lum Berry", "condition": "Usa Extreme Speed (Prioridad +2)", "calculatedSpe": 888 },
    "monB": { "name": "Kingambit", "species": "Kingambit", "nature": "Adamant", "item": "Black Glasses", "condition": "Usa Sucker Punch (Prioridad +1)", "calculatedSpe": 777 },
    "winner": "A",
    "winnerName": "Dragonite",
    "speedDiff": 1,
    "explanation_es": "Extreme Speed opera en prioridad +2 mientras Sucker Punch opera en prioridad +1. Al pertenecer a un bracket superior, Dragonite ataca siempre primero.",
    "explanation_en": "Extreme Speed acts in the +2 Priority bracket, strictly resolving before +1 Priority Sucker Punch regardless of raw speed statistics."
  },
  {
    "id": "SD-31",
    "title": "Benchmark Base 102 vs Base 100: Garchomp vs Volcarona",
    "category": "Base Speed",
    "monA": { "name": "Volcarona", "species": "Volcarona", "nature": "Timid", "item": "Rocky Helmet", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 167 },
    "monB": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 169 },
    "winner": "B",
    "winnerName": "Garchomp",
    "speedDiff": 2,
    "explanation_es": "El Speed Tier Base 102 de Garchomp (169 Spe) supera por exactamente 2 puntos a todo el arquetipo Base 100 (167 Spe) como Volcarona y Charizard-Mega-Y.",
    "explanation_en": "Garchomp's Base 102 speed tier (169 Spe) naturally edges out the entire Base 100 benchmark (167 Spe) by exactly 2 points."
  },
  {
    "id": "SD-32",
    "title": "Caída de Velocidad (-1 Spe): Annihilape a -1 vs Gholdengo",
    "category": "Stat Stages",
    "monA": { "name": "Annihilape", "species": "Annihilape", "nature": "Jolly", "item": "Leftovers", "condition": "Caída de -1 Spe por Icy Wind", "calculatedSpe": 104 },
    "monB": { "name": "Gholdengo", "species": "Gholdengo", "nature": "Timid", "item": "Metal Coat", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 149 },
    "winner": "B",
    "winnerName": "Gholdengo",
    "speedDiff": 45,
    "explanation_es": "Tras un drop de -1 Spe (multiplicador 0.667x), Annihilape cae de 156 a 104 Spe, permitiendo a Gholdengo Timid (149 Spe) superarlo ampliamente.",
    "explanation_en": "After a -1 Spe drop (0.667x), Annihilape plummets from 156 to 104 Spe, allowing Timid Gholdengo (149 Spe) to comfortably attack first."
  },
  {
    "id": "SD-33",
    "title": "Tailwind vs Scarf: Mega Gengar en Tailwind vs Dragapult Scarf",
    "category": "Clima & Tailwind",
    "monA": { "name": "Gengar-Mega", "species": "Gengar-Mega", "nature": "Timid", "item": "Gengarite", "condition": "Bajo Viento Afín (Tailwind x2 Spe)", "calculatedSpe": 400 },
    "monB": { "name": "Dragapult", "species": "Dragapult", "nature": "Timid", "item": "Choice Scarf", "condition": "Equipado con Choice Scarf (x1.5 Spe)", "calculatedSpe": 319 },
    "winner": "A",
    "winnerName": "Gengar-Mega",
    "speedDiff": 81,
    "explanation_es": "Gengar-Mega bajo Tailwind duplica sus 200 Spe alcanzando 400 Spe masivos, superando por 81 puntos a Dragapult Choice Scarf (319 Spe).",
    "explanation_en": "Mega Gengar under Tailwind hits 400 Spe, easily outclassing Choice Scarf Dragapult (319 Spe) by 81 points."
  },
  {
    "id": "SD-34",
    "title": "Trick Room: Rhyperior vs Armarouge",
    "category": "Trick Room",
    "monA": { "name": "Rhyperior", "species": "Rhyperior", "nature": "Brave", "item": "Hard Stone", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 54 },
    "monB": { "name": "Armarouge", "species": "Armarouge", "nature": "Quiet", "item": "Twisted Spoon", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 85 },
    "winner": "A",
    "winnerName": "Rhyperior",
    "speedDiff": 31,
    "explanation_es": "Bajo Espacio Raro el orden se invierte: Rhyperior (Base 40, 54 Spe) es más lento que Armarouge (Base 75, 85 Spe), por lo que Rhyperior ataca primero.",
    "explanation_en": "Under Trick Room, turn order is inverted: Rhyperior (54 Spe) is slower than Armarouge (85 Spe), allowing Rhyperior to move first."
  },
  {
    "id": "SD-35",
    "title": "Duelo Neutral: Gholdengo vs Dragonite (Sin Prioridad)",
    "category": "Base Speed",
    "monA": { "name": "Gholdengo", "species": "Gholdengo", "nature": "Modest", "item": "Life Orb", "condition": "Inversión 32 SP neutra", "calculatedSpe": 136 },
    "monB": { "name": "Dragonite", "species": "Dragonite", "nature": "Adamant", "item": "Lum Berry", "condition": "Inversión 32 SP neutra", "calculatedSpe": 132 },
    "winner": "A",
    "winnerName": "Gholdengo",
    "speedDiff": 4,
    "explanation_es": "A naturaleza neutra con 32 SP, Gholdengo (Base 84, 136 Spe) supera por 4 puntos a Dragonite (Base 80, 132 Spe) si Dragonite no usa Extreme Speed.",
    "explanation_en": "With neutral nature and 32 SP, Gholdengo (Base 84, 136 Spe) outspeeds Dragonite (Base 80, 132 Spe) by 4 points when no priority is clicked."
  },
  {
    "id": "SD-36",
    "title": "Trampa Mega: Garchomp Base vs Mega Garchomp",
    "category": "Mega Evolution",
    "monA": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Forma Base a Máxima Velocidad", "calculatedSpe": 169 },
    "monB": { "name": "Mega Garchomp", "species": "Mega Garchomp", "nature": "Jolly", "item": "Garchompite", "condition": "Forma Mega a Máxima Velocidad", "calculatedSpe": 158 },
    "winner": "A",
    "winnerName": "Garchomp",
    "speedDiff": 11,
    "explanation_es": "¡Trampa clásica de VGC! Mega Garchomp reduce su Velocidad Base de 102 a 92 al Megaevolucionar. Garchomp Base (169 Spe) es 11 puntos más rápido que Mega Garchomp (158 Spe).",
    "explanation_en": "Classic VGC speed trap! Standard Mega Garchomp drops Base Speed from 102 to 92. Base Garchomp (169 Spe) outspeeds Mega Garchomp (158 Spe) by 11 points."
  },
  {
    "id": "SD-37",
    "title": "Parálisis (x0.5 Spe): Meowscarada con Parálisis vs Kingambit",
    "category": "Stat Stages",
    "monA": { "name": "Meowscarada", "species": "Meowscarada", "nature": "Jolly", "item": "Focus Sash", "condition": "Afectado por Parálisis (x0.5 Spe)", "calculatedSpe": 96 },
    "monB": { "name": "Kingambit", "species": "Kingambit", "nature": "Adamant", "item": "Black Glasses", "condition": "Sin inversión en velocidad (0 SP Spe)", "calculatedSpe": 70 },
    "winner": "A",
    "winnerName": "Meowscarada",
    "speedDiff": 26,
    "explanation_es": "Incluso paralizada al 50% de velocidad (96 Spe), la rápida Meowscarada (Base 123) supera por 26 puntos a Kingambit sin inversión en velocidad (70 Spe).",
    "explanation_en": "Even when paralyzed (0.5x speed, 96 Spe), fast Meowscarada still outspeeds 0 Speed SP Kingambit (70 Spe) by 26 points."
  },
  {
    "id": "SD-38",
    "title": "Mismo Bracket de Prioridad (+1): Aqua Jet vs Sucker Punch",
    "category": "Prioridad",
    "monA": { "name": "Basculegion-M", "species": "Basculegion-M", "nature": "Adamant", "item": "Mystic Water", "condition": "Usa Aqua Jet (Prioridad +1)", "calculatedSpe": 130 },
    "monB": { "name": "Kingambit", "species": "Kingambit", "nature": "Adamant", "item": "Black Glasses", "condition": "Usa Sucker Punch (Prioridad +1)", "calculatedSpe": 70 },
    "winner": "A",
    "winnerName": "Basculegion-M",
    "speedDiff": 60,
    "explanation_es": "Al compartir el bracket de prioridad +1, el orden lo dicta la velocidad: Basculegion (130 Spe) supera a Kingambit (70 Spe), impactando Aqua Jet primero.",
    "explanation_en": "Sharing the +1 priority bracket, Level 50 speed determines turn order: Basculegion (130 Spe) beats Kingambit (70 Spe) to hit first."
  },
  {
    "id": "SD-39",
    "title": "Sand Rush: Excadrill en Tormenta de Arena vs Dragapult",
    "category": "Clima & Tailwind",
    "monA": { "name": "Excadrill", "species": "Excadrill", "nature": "Jolly", "item": "Life Orb", "condition": "Habilidad Sand Rush bajo Tormenta de Arena (x2 Spe)", "calculatedSpe": 308 },
    "monB": { "name": "Dragapult", "species": "Dragapult", "nature": "Timid", "item": "Focus Sash", "condition": "Velocidad Máxima 32 SP (+Spe)", "calculatedSpe": 213 },
    "winner": "A",
    "winnerName": "Excadrill",
    "speedDiff": 95,
    "explanation_es": "La habilidad Sand Rush duplica los 154 Spe de Excadrill hasta 308 Spe bajo Tormenta de Arena, superando por 95 puntos a Dragapult (213 Spe).",
    "explanation_en": "Sand Rush doubles Jolly Excadrill from 154 to 308 Spe in Sandstorm, outpacing Dragapult (213 Spe) by 95 points."
  },
  {
    "id": "SD-40",
    "title": "Speed Tier Base: Rotom-Wash vs Metagross",
    "category": "Base Speed",
    "monA": { "name": "Rotom-Wash", "species": "Rotom-Wash", "nature": "Timid", "item": "Sitrus Berry", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 151 },
    "monB": { "name": "Metagross", "species": "Metagross", "nature": "Jolly", "item": "Metal Coat", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 134 },
    "winner": "A",
    "winnerName": "Rotom-Wash",
    "speedDiff": 17,
    "explanation_es": "Rotom-Wash (Base 86, 151 Spe) supera naturalmente a Metagross estándar (Base 70, 134 Spe) por 17 puntos, asegurando Will-O-Wisp antes de recibir un golpe.",
    "explanation_en": "Rotom-Wash (Base 86, 151 Spe) naturally outspeeds standard Metagross (Base 70, 134 Spe) by 17 points, landing Will-O-Wisp first."
  },
  {
    "id": "SD-41",
    "title": "Mega Instantánea: Mega Metagross vs Garchomp",
    "category": "Mega Evolution",
    "monA": { "name": "Mega Metagross", "species": "Mega Metagross", "nature": "Jolly", "item": "Metagrossite", "condition": "Recálculo Instantáneo post-Mega", "calculatedSpe": 178 },
    "monB": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 169 },
    "winner": "A",
    "winnerName": "Mega Metagross",
    "speedDiff": 9,
    "explanation_es": "Metagross base tiene Base 70 (134 Spe), pero al Megaevolucionar escala inmediatamente a Base 110 (178 Spe), superando a Garchomp (169 Spe) por 9 puntos.",
    "explanation_en": "Base Metagross sits at Base 70 (134 Spe), but instantaneous Mega Evolution boosts it to Base 110 (178 Spe), outspeeding Garchomp (169 Spe) by 9 points."
  },
  {
    "id": "SD-42",
    "title": "Choice Scarf: Basculegion-M Scarf vs Mega Charizard Y",
    "category": "Choice Scarf",
    "monA": { "name": "Basculegion-M", "species": "Basculegion-M", "nature": "Jolly", "item": "Choice Scarf", "condition": "Equipado con Choice Scarf (x1.5 Spe)", "calculatedSpe": 214 },
    "monB": { "name": "Charizard-Mega-Y", "species": "Charizard-Mega-Y", "nature": "Timid", "item": "Charizardite Y", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 167 },
    "winner": "A",
    "winnerName": "Basculegion-M",
    "speedDiff": 47,
    "explanation_es": "Basculegion con Choice Scarf alcanza 214 Spe sin depender de lluvia, superando cómodamente a Charizard-Mega-Y Timid (167 Spe) para amenazar OHKO con Wave Crash.",
    "explanation_en": "Choice Scarf Basculegion reaches 214 effective speed without rain, outspeeding Timid Mega Charizard Y (167 Spe) to threaten an instant Wave Crash KO."
  },
  {
    "id": "SD-43",
    "title": "Brackets de Prioridad: Fake Out (+3) vs Grassy Glide (+1)",
    "category": "Prioridad",
    "monA": { "name": "Incineroar", "species": "Incineroar", "nature": "Careful", "item": "Sitrus Berry", "condition": "Usa Fake Out (Prioridad +3)", "calculatedSpe": 999 },
    "monB": { "name": "Rillaboom", "species": "Rillaboom", "nature": "Adamant", "item": "Miracle Seed", "condition": "Usa Grassy Glide en Grassy Terrain (Prioridad +1)", "calculatedSpe": 777 },
    "winner": "A",
    "winnerName": "Incineroar",
    "speedDiff": 1,
    "explanation_es": "Fake Out opera en prioridad +3 y hace retroceder al objetivo antes de que Grassy Glide (+1 prioridad) pueda ejecutarse, ganando el control del turno.",
    "explanation_en": "Fake Out acts in the +3 priority bracket, flinching Rillaboom before its +1 priority Grassy Glide can resolve."
  },
  {
    "id": "SD-44",
    "title": "Speed Tie Oficial Base 100: Mega Charizard Y vs Volcarona",
    "category": "Speed Tie",
    "monA": { "name": "Charizard-Mega-Y", "species": "Charizard-Mega-Y", "nature": "Timid", "item": "Charizardite Y", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 167 },
    "monB": { "name": "Volcarona", "species": "Volcarona", "nature": "Timid", "item": "Rocky Helmet", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 167 },
    "winner": "TIE",
    "winnerName": "Empate (Speed Tie 50/50)",
    "speedDiff": 0,
    "explanation_es": "Ambos comparten Base 100 de Velocidad y alcanzan exactamente 167 Spe con 32 SP y naturaleza favorable. El orden se define por azar puro 50/50.",
    "explanation_en": "Both share Base 100 Speed and hit exact 167 Spe with 32 SP and positive nature. Turn order is determined by a 50/50 engine coinflip."
  },
  {
    "id": "SD-45",
    "title": "Boost de Velocidad (+1): Quaquaval tras Aqua Step vs Meowscarada",
    "category": "Stat Stages",
    "monA": { "name": "Quaquaval", "species": "Quaquaval", "nature": "Jolly", "item": "Mystic Water", "condition": "Boost de +1 Spe tras Aqua Step", "calculatedSpe": 225 },
    "monB": { "name": "Meowscarada", "species": "Meowscarada", "nature": "Jolly", "item": "Focus Sash", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 192 },
    "winner": "A",
    "winnerName": "Quaquaval",
    "speedDiff": 33,
    "explanation_es": "Tras ganar +1 en Velocidad con Aqua Step (1.5x), Quaquaval escala de 150 a 225 Spe, superando con creces a Meowscarada a máxima velocidad (192 Spe).",
    "explanation_en": "With +1 Speed from Aqua Step (1.5x), Quaquaval surges from 150 to 225 Spe, cleanly outpacing maximum speed Meowscarada (192 Spe)."
  },
  {
    "id": "SD-46",
    "title": "Clima vs Tailwind: Basculegion en Lluvia vs Whimsicott en Tailwind",
    "category": "Clima & Tailwind",
    "monA": { "name": "Basculegion-M", "species": "Basculegion-M", "nature": "Modest", "item": "Life Orb", "condition": "Habilidad Swift Swim bajo Lluvia activa (x2 Spe)", "calculatedSpe": 260 },
    "monB": { "name": "Whimsicott", "species": "Whimsicott", "nature": "Timid", "item": "Mental Herb", "condition": "Bajo Viento Afín (Tailwind x2 Spe)", "calculatedSpe": 368 },
    "winner": "B",
    "winnerName": "Whimsicott",
    "speedDiff": 108,
    "explanation_es": "Whimsicott bajo Tailwind alcanza 368 Spe masivos (184 x 2), superando por 108 puntos a Basculegion Modest en lluvia con Swift Swim (260 Spe).",
    "explanation_en": "Tailwind Whimsicott hits 368 Spe (184 x 2), outpacing Modest Swift Swim Basculegion in Rain (260 Spe) by 108 points."
  },
  {
    "id": "SD-47",
    "title": "Trick Room: Skeledirge vs Torkoal",
    "category": "Trick Room",
    "monA": { "name": "Skeledirge", "species": "Skeledirge", "nature": "Quiet", "item": "Leftovers", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 77 },
    "monB": { "name": "Torkoal", "species": "Torkoal", "nature": "Quiet", "item": "Heat Rock", "condition": "Bajo Espacio Raro (Trick Room)", "calculatedSpe": 22 },
    "winner": "B",
    "winnerName": "Torkoal",
    "speedDiff": 55,
    "explanation_es": "En Trick Room el más lento ataca primero. Torkoal (Base 20, 22 Spe) es mucho más lento que Skeledirge (Base 66, 77 Spe), ganando la iniciativa para usar Eruption.",
    "explanation_en": "Under Trick Room, the slower Pokemon moves first. Torkoal (22 Spe) is much slower than Skeledirge (77 Spe), securing turn priority for Eruption."
  },
  {
    "id": "SD-48",
    "title": "Speed Tie Bulky Base 60: Incineroar vs Grimmsnarl",
    "category": "Speed Tie",
    "monA": { "name": "Incineroar", "species": "Incineroar", "nature": "Careful", "item": "Sitrus Berry", "condition": "Sin inversión en velocidad (0 SP Spe)", "calculatedSpe": 80 },
    "monB": { "name": "Grimmsnarl", "species": "Grimmsnarl", "nature": "Careful", "item": "Light Clay", "condition": "Sin inversión en velocidad (0 SP Spe)", "calculatedSpe": 80 },
    "winner": "TIE",
    "winnerName": "Empate (Speed Tie 50/50)",
    "speedDiff": 0,
    "explanation_es": "Ambos comparten Base 60 y exactamente 80 Spe a Nivel 50 sin inversión en velocidad. Cualquier ataque sin prioridad se resuelve con un lanzamiento de moneda 50/50.",
    "explanation_en": "Both share Base 60 and exact 80 Spe at Level 50 with 0 Speed SP. Any non-priority attack is resolved by a pure 50/50 speed tie."
  },
  {
    "id": "SD-49",
    "title": "Choice Scarf Sorpresa: Tyranitar Scarf vs Garchomp",
    "category": "Choice Scarf",
    "monA": { "name": "Tyranitar", "species": "Tyranitar", "nature": "Jolly", "item": "Choice Scarf", "condition": "Equipado con Choice Scarf (x1.5 Spe)", "calculatedSpe": 186 },
    "monB": { "name": "Garchomp", "species": "Garchomp", "nature": "Jolly", "item": "Life Orb", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 169 },
    "winner": "A",
    "winnerName": "Tyranitar",
    "speedDiff": 17,
    "explanation_es": "Tyranitar Jolly con Choice Scarf escala a 186 Spe efectivos, superando a Garchomp Jolly (169 Spe) por 17 puntos para castigar con un ataque de cobertura antes de recibir daño.",
    "explanation_en": "Jolly Choice Scarf Tyranitar surges to 186 Spe, outspeeding Jolly Garchomp (169 Spe) by 17 points to strike first before taking damage."
  },
  {
    "id": "SD-50",
    "title": "Mega Instantánea: Mega Garchomp Z vs Dragapult",
    "category": "Mega Evolution",
    "monA": { "name": "Mega Garchomp Z", "species": "Mega Garchomp Z", "nature": "Jolly", "item": "Garchompite Z", "condition": "Recálculo Instantáneo post-Mega", "calculatedSpe": 223 },
    "monB": { "name": "Dragapult", "species": "Dragapult", "nature": "Timid", "item": "Life Orb", "condition": "Inversión 32 SP (+Spe)", "calculatedSpe": 213 },
    "winner": "A",
    "winnerName": "Mega Garchomp Z",
    "speedDiff": 10,
    "explanation_es": "Mega Garchomp Z posee una exorbitante Base 151 de Velocidad alcanzando 223 Spe al instante, destronando incluso a Dragapult a máxima velocidad (213 Spe) por 10 puntos.",
    "explanation_en": "Mega Garchomp Z reaches a massive Base 151 Speed hitting 223 Spe instantly, surpassing even maximum speed Dragapult (213 Spe) by 10 points."
  }
]

assert len(SPEED_DUELS) == 50, f"Expected 50 duels, got {len(SPEED_DUELS)}"
print(f"Verified {len(SPEED_DUELS)} Speed Duels successfully.")

# Write to engine/speed_duels_data.py
SPEED_DATA_PATH = REPO_ROOT / "engine" / "speed_duels_data.py"
with open(SPEED_DATA_PATH, "w", encoding="utf-8") as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write('"""\nCoach Porygon VGC — Speed Duel Scenarios\n50 Level 50 Speed Reflex Matchups\n"""\n\n')
    f.write("SPEED_DUELS = ")
    f.write(json.dumps(SPEED_DUELS, indent=2, ensure_ascii=False))
    f.write("\n")

print(f"Updated {SPEED_DATA_PATH} with 50 Speed Duels.")

# Write to data/Speed_Duel_Scenarios.csv
SPEED_CSV_PATH = REPO_ROOT / "data" / "Speed_Duel_Scenarios.csv"
fieldnames = [
    "Duel_ID", "Title", "Category",
    "MonA_Name", "MonA_Nature", "MonA_Item", "MonA_Condition", "MonA_Calculated_Spe",
    "MonB_Name", "MonB_Nature", "MonB_Item", "MonB_Condition", "MonB_Calculated_Spe",
    "Winner", "Winner_Name", "Speed_Difference",
    "Explanation_ES", "Explanation_EN"
]

with open(SPEED_CSV_PATH, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(fieldnames)
    for d in SPEED_DUELS:
        writer.writerow([
            d["id"], d["title"], d["category"],
            d["monA"]["name"], d["monA"]["nature"], d["monA"]["item"], d["monA"]["condition"], d["monA"]["calculatedSpe"],
            d["monB"]["name"], d["monB"]["nature"], d["monB"]["item"], d["monB"]["condition"], d["monB"]["calculatedSpe"],
            d["winner"], d["winnerName"], d["speedDiff"],
            d["explanation_es"], d["explanation_en"]
        ])

print(f"Updated {SPEED_CSV_PATH} with 50 Speed Duels.")

# Also update tests/data/Speed_Duel_Scenarios.csv
TEST_CSV_PATH = REPO_ROOT / "tests" / "data" / "Speed_Duel_Scenarios.csv"
if TEST_CSV_PATH.parent.exists():
    with open(TEST_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for d in SPEED_DUELS:
            writer.writerow([
                d["id"], d["title"], d["category"],
                d["monA"]["name"], d["monA"]["nature"], d["monA"]["item"], d["monA"]["condition"], d["monA"]["calculatedSpe"],
                d["monB"]["name"], d["monB"]["nature"], d["monB"]["item"], d["monB"]["condition"], d["monB"]["calculatedSpe"],
                d["winner"], d["winnerName"], d["speedDiff"],
                d["explanation_es"], d["explanation_en"]
            ])
    print(f"Updated {TEST_CSV_PATH} with 50 Speed Duels.")
