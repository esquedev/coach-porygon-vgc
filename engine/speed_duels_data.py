# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Speed Duel Scenarios
25 Level 50 Speed Reflex Matchups
"""

SPEED_DUELS = [
  {
    "id": "SD-01",
    "title": "Base Speed: Garchomp vs Charizard-Mega-Y",
    "category": "Base Speed",
    "monA": {
      "name": "Garchomp",
      "nature": "Jolly",
      "item": "Life Orb",
      "condition": "Inversión 32 SP (+Spe)",
      "calculatedSpe": 169
    },
    "monB": {
      "name": "Charizard-Mega-Y",
      "nature": "Timid",
      "item": "Charizardite Y",
      "condition": "Inversión 32 SP (+Spe)",
      "calculatedSpe": 167
    },
    "winner": "A",
    "winnerName": "Garchomp",
    "speedDiff": 2,
    "explanation_es": "Garchomp Jolly con 32 SP alcanza 169 Spe a Nivel 50, superando por 2 puntos a Charizard-Mega-Y Timid con 32 SP (167 Spe). Garchomp ataca primero.",
    "explanation_en": "Jolly Garchomp with 32 SP reaches 169 Spe at Level 50, outspeeding Timid Charizard-Mega-Y (167 Spe) by 2 points. Garchomp attacks first."
  },
  {
    "id": "SD-02",
    "title": "Mega Instantánea: Lucario-Mega vs Garchomp",
    "category": "Mega Evolution",
    "monA": {
      "name": "Lucario-Mega",
      "nature": "Timid",
      "item": "Lucarionite",
      "condition": "Recálculo Instantáneo post-Mega",
      "calculatedSpe": 180
    },
    "monB": {
      "name": "Garchomp",
      "nature": "Jolly",
      "item": "Life Orb",
      "condition": "Inversión 32 SP (+Spe)",
      "calculatedSpe": 169
    },
    "winner": "A",
    "winnerName": "Lucario-Mega",
    "speedDiff": 11,
    "explanation_es": "En Regulation M-C la Mega Evolución actualiza la velocidad de inmediato en el mismo turno. Lucario-Mega (112 Base) llega a 180 Spe y supera a Garchomp (169 Spe) por 11 puntos.",
    "explanation_en": "In Regulation M-C, Mega Evolution recalculates speed instantly. Mega Lucario (112 Base) reaches 180 Spe and outspeeds Garchomp (169 Spe) by 11 points."
  },
  {
    "id": "SD-03",
    "title": "Swift Swim vs Unburden: Basculegion en Lluvia vs Sneasler Unburden",
    "category": "Clima & Habilidad",
    "monA": {
      "name": "Basculegion-M",
      "nature": "Modest",
      "item": "Life Orb",
      "condition": "Habilidad Swift Swim bajo Lluvia activa",
      "calculatedSpe": 260
    },
    "monB": {
      "name": "Sneasler",
      "nature": "Jolly",
      "item": "Electric Seed",
      "condition": "Habilidad Unburden activada tras Electric Seed",
      "calculatedSpe": 378
    },
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
    "monA": {
      "name": "Incineroar",
      "nature": "Careful",
      "item": "Sitrus Berry",
      "condition": "Usa Fake Out (Prioridad +3)",
      "calculatedSpe": 999
    },
    "monB": {
      "name": "Dragonite",
      "nature": "Adamant",
      "item": "Lum Berry",
      "condition": "Usa Extreme Speed (Prioridad +2)",
      "calculatedSpe": 888
    },
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
    "monA": {
      "name": "Rillaboom",
      "nature": "Adamant",
      "item": "Miracle Seed",
      "condition": "Grassy Glide en Grassy Terrain (+1 Prioridad)",
      "calculatedSpe": 117
    },
    "monB": {
      "name": "Kingambit",
      "nature": "Adamant",
      "item": "Black Glasses",
      "condition": "Sucker Punch (+1 Prioridad)",
      "calculatedSpe": 70
    },
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
    "monA": {
      "name": "Archaludon",
      "nature": "Timid",
      "item": "Choice Scarf",
      "condition": "Equipado con Choice Scarf (x1.5 Spe)",
      "calculatedSpe": 205
    },
    "monB": {
      "name": "Gengar-Mega",
      "nature": "Timid",
      "item": "Gengarite",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 200
    },
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
    "monA": {
      "name": "Torkoal",
      "nature": "Quiet",
      "item": "Heat Rock",
      "condition": "Bajo Espacio Raro (Trick Room)",
      "calculatedSpe": 22
    },
    "monB": {
      "name": "Farigiraf",
      "nature": "Quiet",
      "item": "Mental Herb",
      "condition": "Bajo Espacio Raro (Trick Room)",
      "calculatedSpe": 58
    },
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
    "monA": {
      "name": "Primarina",
      "nature": "Modest",
      "item": "Mystic Water",
      "condition": "Caída de -1 Spe por Electroweb",
      "calculatedSpe": 74
    },
    "monB": {
      "name": "Armarouge",
      "nature": "Modest",
      "item": "Life Orb",
      "condition": "Velocidad neutral sin modificadores",
      "calculatedSpe": 95
    },
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
    "monA": {
      "name": "Sneasler",
      "nature": "Jolly",
      "item": "Focus Sash",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 189
    },
    "monB": {
      "name": "Gengar-Mega",
      "nature": "Timid",
      "item": "Gengarite",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 200
    },
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
    "monA": {
      "name": "Charizard-Mega-Y",
      "nature": "Timid",
      "item": "Charizardite Y",
      "condition": "Bajo Viento Afín (Tailwind x2 Spe)",
      "calculatedSpe": 334
    },
    "monB": {
      "name": "Basculegion-M",
      "nature": "Modest",
      "item": "Life Orb",
      "condition": "Bajo Lluvia activa (Swift Swim x2 Spe)",
      "calculatedSpe": 260
    },
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
    "monA": {
      "name": "Dragonite",
      "nature": "Jolly",
      "item": "Choice Scarf",
      "condition": "Equipado con Choice Scarf (x1.5 Spe)",
      "calculatedSpe": 217
    },
    "monB": {
      "name": "Lucario-Mega",
      "nature": "Timid",
      "item": "Lucarionite",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 180
    },
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
    "monA": {
      "name": "Raichu-Mega-X",
      "nature": "Timid",
      "item": "Raichunite X",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 178
    },
    "monB": {
      "name": "Garchomp",
      "nature": "Jolly",
      "item": "Life Orb",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 169
    },
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
    "monA": {
      "name": "Incineroar",
      "nature": "Careful",
      "item": "Sitrus Berry",
      "condition": "Sin inversión en velocidad (0 SP Spe)",
      "calculatedSpe": 80
    },
    "monB": {
      "name": "Primarina",
      "nature": "Modest",
      "item": "Mystic Water",
      "condition": "Sin inversión en velocidad (0 SP Spe)",
      "calculatedSpe": 80
    },
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
    "monA": {
      "name": "Talonflame",
      "nature": "Jolly",
      "item": "Mental Herb",
      "condition": "Gale Wings a 100% HP (Tailwind +1 Prio)",
      "calculatedSpe": 195
    },
    "monB": {
      "name": "Whimsicott",
      "nature": "Timid",
      "item": "Mental Herb",
      "condition": "Prankster (Tailwind +1 Prio)",
      "calculatedSpe": 184
    },
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
    "monA": {
      "name": "Annihilape",
      "nature": "Adamant",
      "item": "Leftovers",
      "condition": "Boost de +1 Spe activo",
      "calculatedSpe": 213
    },
    "monB": {
      "name": "Gengar-Mega",
      "nature": "Timid",
      "item": "Gengarite",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 200
    },
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
    "monA": {
      "name": "Armarouge",
      "nature": "Modest",
      "item": "Life Orb",
      "condition": "Boost de +2 Spe tras activar Weak Armor",
      "calculatedSpe": 254
    },
    "monB": {
      "name": "Sneasler",
      "nature": "Jolly",
      "item": "Focus Sash",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 189
    },
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
    "monA": {
      "name": "Maushold",
      "nature": "Jolly",
      "item": "Focus Sash",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 179
    },
    "monB": {
      "name": "Charizard-Mega-Y",
      "nature": "Timid",
      "item": "Charizardite Y",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 167
    },
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
    "monA": {
      "name": "Garchomp",
      "nature": "Jolly",
      "item": "Life Orb",
      "condition": "Bajo Viento Afín (Tailwind x2 Spe)",
      "calculatedSpe": 338
    },
    "monB": {
      "name": "Dragapult",
      "nature": "Timid",
      "item": "Twisted Spoon",
      "condition": "Velocidad Máxima 32 SP (+Spe)",
      "calculatedSpe": 213
    },
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
    "monA": {
      "name": "Tyranitar",
      "nature": "Brave",
      "item": "Rocky Helmet",
      "condition": "Bajo Espacio Raro (Trick Room)",
      "calculatedSpe": 63
    },
    "monB": {
      "name": "Kingambit",
      "nature": "Brave",
      "item": "Black Glasses",
      "condition": "Bajo Espacio Raro (Trick Room)",
      "calculatedSpe": 49
    },
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
    "monA": {
      "name": "Basculegion-M",
      "nature": "Modest",
      "item": "Life Orb",
      "condition": "Habilidad Swift Swim bajo Lluvia activa",
      "calculatedSpe": 260
    },
    "monB": {
      "name": "Dragapult",
      "nature": "Timid",
      "item": "Choice Scarf",
      "condition": "Equipado con Choice Scarf (x1.5 Spe)",
      "calculatedSpe": 319
    },
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
    "monA": {
      "name": "Lucario-Mega",
      "nature": "Timid",
      "item": "Lucarionite",
      "condition": "Recálculo Instantáneo post-Mega",
      "calculatedSpe": 180
    },
    "monB": {
      "name": "Talonflame",
      "nature": "Jolly",
      "item": "Mental Herb",
      "condition": "Movimiento estándar sin prioridad",
      "calculatedSpe": 195
    },
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
    "monA": {
      "name": "Rillaboom",
      "nature": "Adamant",
      "item": "Miracle Seed",
      "condition": "Inversión bulky moderada (12 SP Spe)",
      "calculatedSpe": 117
    },
    "monB": {
      "name": "Incineroar",
      "nature": "Careful",
      "item": "Sitrus Berry",
      "condition": "Inversión bulky baja (4 SP Spe)",
      "calculatedSpe": 85
    },
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
    "monA": {
      "name": "Whimsicott",
      "nature": "Timid",
      "item": "Mental Herb",
      "condition": "Tailwind con Prankster (+1 Prioridad)",
      "calculatedSpe": 184
    },
    "monB": {
      "name": "Rillaboom",
      "nature": "Adamant",
      "item": "Rocky Helmet",
      "condition": "Ejecuta Fake Out (Prioridad +3)",
      "calculatedSpe": 999
    },
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
    "monA": {
      "name": "Pelipper",
      "nature": "Bold",
      "item": "Damp Rock",
      "condition": "Sin inversión en velocidad (0 SP Spe)",
      "calculatedSpe": 85
    },
    "monB": {
      "name": "Torkoal",
      "nature": "Quiet",
      "item": "Heat Rock",
      "condition": "Sin inversión en velocidad (0 SP Spe)",
      "calculatedSpe": 40
    },
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
    "monA": {
      "name": "Garchomp",
      "nature": "Jolly",
      "item": "Life Orb",
      "condition": "Bajo Viento Afín (Tailwind x2 Spe)",
      "calculatedSpe": 338
    },
    "monB": {
      "name": "Sneasler",
      "nature": "Jolly",
      "item": "Electric Seed",
      "condition": "Habilidad Unburden activada tras Electric Seed",
      "calculatedSpe": 378
    },
    "winner": "B",
    "winnerName": "Sneasler",
    "speedDiff": 40,
    "explanation_es": "Sneasler con Unburden alcanza 378 Spe masivos (Base 120 x 2), superando incluso a Garchomp bajo Tailwind (Base 102 x 2 = 338 Spe) por 40 puntos.",
    "explanation_en": "Unburden Sneasler hits 378 Spe, outspeeding even Tailwind Garchomp (338 Spe) by 40 points."
  }
]
