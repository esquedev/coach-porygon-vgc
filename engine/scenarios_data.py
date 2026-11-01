true = True
false = False
null = None
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Mode 3 Flashcard Sparring Scenarios
42 Deterministic Scenarios (SC-01 to SC-42) with 4 options each (168 Total Options)
"""

CRUCIBLE_SCENARIOS = [
  {
    "id": "SC-01",
    "title": "M308 Turno 1: POS-02 Lead Compression vs Unburden Sneasler + Pelipper Rain",
    "driver": "Autopilot",
    "code": "POS-02",
    "turnBadge": "TURNO 1 • LLUVIA ACTIVA • VP 4v4 (+0.0)",
    "context": "Abriste Garchomp + Rotom-Wash ante Sneasler (Focus Sash) + Pelipper (Damp Rock). Pelipper activa Drizzle. Si haces un cambio seco o atacas sin cubrir el slot de Garchomp, Sneasler amenaza Fake Out + Close Combat, mientras Pelipper presiona con Weather Ball / Hurricane.",
    "oppSlots": [
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 100,
        "status": "Spe 189"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 100,
        "status": "Rain 5T"
      }
    ],
    "mySlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Spe 169"
      },
      {
        "name": "Rotom-Wash",
        "item": "Sitrus Berry",
        "ability": "Levitate",
        "hp": 100,
        "status": "Spe 115"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Garchomp Protect + Rotom-Wash Electroweb",
        "optimal": true,
        "vpDelta": "+1.35 VP",
        "log": [
          "1. Garchomp usó Protect! Se protege de cualquier doble foco o Fake Out.",
          "2. Sneasler usó Fake Out sobre Rotom-Wash (-14% HP), consumiendo el turno 1 de presión.",
          "3. Pelipper usó Hurricane sobre el Protect de Garchomp (Bloqueado).",
          "4. Rotom-Wash usó Electroweb! Daña a ambos rivales y reduce la velocidad de Sneasler y Pelipper a -1 Spe.",
          "5. [PROYECCIÓN TURNO +2]: Con Sneasler a -1 Spe (126 Spe efectivo), Garchomp (169 Spe) actúa primero y asegura el KO limpio con Stomping Tantrum sin activar Unburden. Rotom-Wash remata a Pelipper con Thunderbolt.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Ventaja de 4v2 con el clima neutralizado y ambos sweepers del entrenador intactos (+1.35 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.35 VP): Neutralizas el turno de Fake Out sin exponer a Garchomp ni regalar un Dry Hard Switch (POS-01). En T+2 tienes control absoluto de velocidad y checkmate posicional sobre el núcleo de lluvia rival.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Con Sneasler a -1 Spe (126 Spe efectivo), Garchomp (169 Spe) actúa primero y asegura el KO limpio con Stomping Tantrum sin activar Unburden. Rotom-Wash remata a Pelipper con Thunderbolt. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Ventaja de 4v2 con el clima neutralizado y ambos sweepers del entrenador intactos (+1.35 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Cambiar Garchomp → Corviknight + Rotom-Wash Thunderbolt a Pelipper",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Retiras a Garchomp → Entra Corviknight en seco.",
          "2. Sneasler usó Close Combat en el slot de Garchomp → Golpea a Corviknight por 58% HP!",
          "3. Pelipper usó Weather Ball (Rain STAB) en el mismo slot → Corviknight cae debilitado (0% HP)!",
          "4. Rotom-Wash Thunderbolt debilita a Pelipper, pero pierdes a tu mejor pivot de acero.",
          "5. [PROYECCIÓN TURNO +2]: Corviknight fainted en T1 (déficit 3v4). Sneasler conserva Unburden y Focus Sash intacto amenazando con barrer a Rotom-Wash y Garchomp con Close Combat.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Tablero completamente colapsado bajo lluvia rival; 0% de equidad de victoria."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar en seco ante doble amenaza ofensiva regala a tu mejor pivot de acero y entrega el tempo completo del match (-1.50 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Corviknight fainted en T1 (déficit 3v4). Sneasler conserva Unburden y Focus Sash intacto amenazando con barrer a Rotom-Wash y Garchomp con Close Combat. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Tablero completamente colapsado bajo lluvia rival; 0% de equidad de victoria."
      },
      {
        "id": "OPT-C",
        "label": "C) Garchomp Stomping Tantrum a Sneasler + Rotom-Wash Volt Switch a Pelipper",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Sneasler usó Fake Out en Garchomp (-15% HP) → ¡Garchomp retrocede y pierde su acción!",
          "2. Pelipper usó Hurricane sobre Rotom-Wash (-52% HP) y lo confunde.",
          "3. Rotom-Wash Volt Switch conecta en Pelipper pero este sobrevive con 22% HP.",
          "4. En Turno 2, Sneasler conserva Focus Sash intacto y amenaza con barrer a tu equipo.",
          "5. [PROYECCIÓN TURNO +2]: Garchomp retrocedió en T1 y Rotom-Wash quedó confundido al 48% HP. Sneasler amenaza Close Combat letal sobre Garchomp.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pelipper mete Tailwind o Hurricane sin castigo, consolidando un 2-0 irrecuperable en ventaja de piezas."
        ],
        "verdict": "❌ FUGA TÁCTICA (Autopilot / Greed): Atacar sin cubrir el Fake Out obvio te hace perder el turno de tu atacante principal (-1.25 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Garchomp retrocedió en T1 y Rotom-Wash quedó confundido al 48% HP. Sneasler amenaza Close Combat letal sobre Garchomp. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pelipper mete Tailwind o Hurricane sin castigo, consolidando un 2-0 irrecuperable en ventaja de piezas."
      },
      {
        "id": "OPT-D",
        "label": "D) Garchomp Dragon Claw a Pelipper + Rotom-Wash Hydro Pump a Sneasler",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Sneasler usa Close Combat sobre Garchomp (-68% HP) y activa Rough Skin.",
          "2. Pelipper ejecuta Tailwind bajo Lluvia, duplicando la velocidad del bando rival!",
          "3. Garchomp Dragon Claw deja a Pelipper en 34% HP.",
          "4. Rotom-Wash Hydro Pump acierta pero Sneasler resiste con Focus Sash (1 HP). Ahora el rival tiene Tailwind y Unburden activos.",
          "5. [PROYECCIÓN TURNO +2]: El rival tiene Tailwind activo (3T restantes) y Sneasler activó Unburden al quedar a 1 HP con Focus Sash. Su velocidad efectiva supera los 378 Spe.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Doble sweep inminente sobre Garchomp y Rotom-Wash antes de que puedan seleccionar movimiento."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Damage Overkill / Mal targeting): Ignorar al setter de Tailwind bajo lluvia permite al rival duplicar su velocidad y barrer tu retaguardia (-1.40 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: El rival tiene Tailwind activo (3T restantes) y Sneasler activó Unburden al quedar a 1 HP con Focus Sash. Su velocidad efectiva supera los 378 Spe. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Doble sweep inminente sobre Garchomp y Rotom-Wash antes de que puedan seleccionar movimiento."
      }
    ]
  },
  {
    "id": "SC-02",
    "title": "M311 Turno 2: POS-01 Dry Hard Switch ante Archaludon Electro Shot + Pelipper",
    "driver": "Autopilot",
    "code": "POS-01",
    "turnBadge": "TURNO 2 • LLUVIA ACTIVA • VP 4v4",
    "context": "Tienes a Charizard-Mega-Y y Farigiraf en campo, pero Pelipper entró de cambio el turno previo y sobreescribió tu Sol con Lluvia. Archaludon amenaza Electro Shot en 1 turno sin necesidad de cargar.",
    "oppSlots": [
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 94,
        "status": "Electro Shot Ready"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 100,
        "status": "Tailwind Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Charizard-Mega-Y",
        "item": "Charizardite Y",
        "ability": "Drought",
        "hp": 100,
        "status": "Expuesto a Elec"
      },
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 90,
        "status": "Trick Room Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard-Mega-Y Protect + Farigiraf Trick Room",
        "optimal": true,
        "vpDelta": "+1.60 VP",
        "log": [
          "1. Charizard-Mega-Y usa Protect y bloquea el Electro Shot (+1 SpA) de Archaludon!",
          "2. Pelipper usa Hurricane sobre Farigiraf (-40% HP). Armor Tail previene cualquier interferencia.",
          "3. Farigiraf ejecuta Trick Room con éxito!",
          "4. Dimensiones distorsionadas: en Turno 3 tus atacantes lentos se mueven primero.",
          "5. [PROYECCIÓN TURNO +2]: Trick Room activo (4T restantes). Farigiraf y Charizard-Mega-Y (o switch a Ursaluna/Torkoal) se mueven antes que Archaludon y Pelipper.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Reviertes la lluvia reactivando Sol con switch o castigas con ataques coordinados bajo dimensiones distorsionadas (+1.60 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.60 VP): Neutralizas el nuke eléctrico con Protect mientras Farigiraf invierte el orden de velocidad a tu favor, garantizando iniciativa total en T+2 y T+3.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Trick Room activo (4T restantes). Farigiraf y Charizard-Mega-Y (o switch a Ursaluna/Torkoal) se mueven antes que Archaludon y Pelipper. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Reviertes la lluvia reactivando Sol con switch o castigas con ataques coordinados bajo dimensiones distorsionadas (+1.60 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Cambiar Charizard-Mega-Y → Garchomp + Farigiraf Psychic a Archaludon",
        "optimal": false,
        "vpDelta": "-1.75 VP",
        "log": [
          "1. Retiras a Charizard-Mega-Y → Entra Garchomp en seco.",
          "2. Archaludon redirige su Electro Shot o dispara a Farigiraf (-55% HP).",
          "3. Pelipper usa Weather Ball de Agua potenciada por Lluvia sobre el slot de Garchomp: ¡OHKO masivo (0% HP)!",
          "4. Pierdes a tu principal atacante físico antes de que pueda tocar el campo.",
          "5. [PROYECCIÓN TURNO +2]: Garchomp fainted al entrar (0% HP). Farigiraf queda solo en campo a 45% HP frente a Archaludon con +1 Sp. Atk.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Archaludon ejecuta Flash Cannon y barre a Farigiraf; pierdes tu respuesta de velocidad."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar a un atacante frágil directamente a una Lluvia activa regala tu condición de victoria (-1.75 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Garchomp fainted al entrar (0% HP). Farigiraf queda solo en campo a 45% HP frente a Archaludon con +1 Sp. Atk. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Archaludon ejecuta Flash Cannon y barre a Farigiraf; pierdes tu respuesta de velocidad."
      },
      {
        "id": "OPT-C",
        "label": "C) Charizard-Mega-Y Heat Wave en Lluvia + Farigiraf Hyper Voice",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. En Lluvia, el poder de Heat Wave se reduce al 50%.",
          "2. Archaludon recibe daño mínimo (18% HP) y activa Stamina (+1 Def).",
          "3. Archaludon desata Electro Shot en 1 turno sobre Charizard-Mega-Y: ¡OHKO definitivo (0% HP)!",
          "4. Farigiraf queda aislado en campo contra dos atacantes bajo lluvia.",
          "5. [PROYECCIÓN TURNO +2]: Charizard-Mega-Y debilitado (0% HP). Archaludon tiene +1 SpA y Stamina (+1 Def) por el Heat Wave débil.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Farigiraf no puede remontar solo contra dos amenazas potenciadas bajo clima rival."
        ],
        "verdict": "❌ FUGA TÁCTICA (Autopilot / SPD-02): Lanzar ataques de Fuego bajo clima adverso sin resetear el sol condena a tu Mega (-1.45 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Charizard-Mega-Y debilitado (0% HP). Archaludon tiene +1 SpA y Stamina (+1 Def) por el Heat Wave débil. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Farigiraf no puede remontar solo contra dos amenazas potenciadas bajo clima rival."
      },
      {
        "id": "OPT-D",
        "label": "D) Charizard-Mega-Y Solar Beam a Pelipper + Farigiraf Protect pasivo",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. En Lluvia, Solar Beam requiere 2 turnos de carga completa!",
          "2. Charizard queda inmovilizado absorbiendo energía solar bajo la tormenta.",
          "3. Archaludon ejecuta Electro Shot y fulmina a Charizard (0% HP).",
          "4. Farigiraf quema su Protect de forma pasiva sin haber cambiado el estado del tablero.",
          "5. [PROYECCIÓN TURNO +2]: Charizard fainted en el turno de carga de Solar Beam. Farigiraf quemó Protect y ahora enfrenta doble foco rival.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida total de presencia ofensiva sin haber tocado a los rivales."
        ],
        "verdict": "❌ FUGA TÁCTICA (Format Divergence / MEC-02): Olvidar la mecánica de Solar Beam en lluvia pierde el slot ofensivo por completo (-1.60 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Charizard fainted en el turno de carga de Solar Beam. Farigiraf quemó Protect y ahora enfrenta doble foco rival. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida total de presencia ofensiva sin haber tocado a los rivales."
      }
    ]
  },
  {
    "id": "SC-03",
    "title": "M315 Turno 1: SPD-02 Secuencia de Clima/Terreno (Rillaboom vs Indeedee / Armarouge)",
    "driver": "Autopilot",
    "code": "SPD-02",
    "turnBadge": "TURNO 1 • PSYCHIC TERRAIN ACTIVO • VP 4v4",
    "context": "Abriste Rillaboom (Grassy Surge) e Incineroar frente a Indeedee-F (Psychic Surge) y Armarouge (Expanding Force). Indeedee es más lenta (Spe base 85 vs Rillaboom Spe base 85 con inversión mínima) y su Psychic Surge sobreescribió tu Grassy Terrain al inicio del turno.",
    "oppSlots": [
      {
        "name": "Indeedee-F",
        "item": "Psychic Seed",
        "ability": "Psychic Surge",
        "hp": 100,
        "status": "Terrain Active"
      },
      {
        "name": "Armarouge",
        "item": "Life Orb",
        "ability": "Flash Fire",
        "hp": 100,
        "status": "Expanding Force"
      }
    ],
    "mySlots": [
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 100,
        "status": "Glide Locked"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Fake Out Blocked"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom U-turn en Indeedee + Incineroar Knock Off en Armarouge",
        "optimal": true,
        "vpDelta": "+1.55 VP",
        "log": [
          "1. U-turn y Knock Off no tienen prioridad, por lo que NO colisionan con Psychic Terrain ni Armor Tail.",
          "2. Incineroar Knock Off impacta a Armarouge (-58% HP) y despoja su Life Orb!",
          "3. Rillaboom U-turn impacta super efectivo a Indeedee (-54% HP) y pivota limpiamente hacia un compañero seguro.",
          "4. Neutralizas la presión de Expanding Force sin regalar ningún turno.",
          "5. [PROYECCIÓN TURNO +2]: Rillaboom en retaguardia listo para volver a entrar y sobreescribir Psychic Terrain con Grassy Surge. Armarouge sin Life Orb pierde el rango de OHKO de Expanding Force.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Reset del terreno desactiva el bonus de Expanding Force y reactiva Grassy Glide prioritario para cerrar el juego (+1.55 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.55 VP): Castigas el núcleo psíquico con ataques sin prioridad y reposicionas a tu equipo sin chocar con el terreno, preparando el reingreso de Grassy Surge en T+2.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Rillaboom en retaguardia listo para volver a entrar y sobreescribir Psychic Terrain con Grassy Surge. Armarouge sin Life Orb pierde el rango de OHKO de Expanding Force. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Reset del terreno desactiva el bonus de Expanding Force y reactiva Grassy Glide prioritario para cerrar el juego (+1.55 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Rillaboom Grassy Glide en Indeedee + Incineroar Fake Out en Armarouge",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Incineroar intenta usar Fake Out... ¡Bloqueado por Psychic Terrain en el suelo!",
          "2. Rillaboom intenta usar Grassy Glide... ¡Falla debido al Psychic Terrain!",
          "3. Armarouge usa Expanding Force potenciado en área: ¡doble golpe demoledor (-78% a ambos slots)!",
          "4. Indeedee usa Dazzling Gleam y asegura un doble KO demoledor en Turno 1.",
          "5. [PROYECCIÓN TURNO +2]: Fake Out y Grassy Glide fallaron en T1 por Psychic Terrain. Armarouge usó Expanding Force con boost de terreno y Life Orb, barriendo a Rillaboom y dejando a Incineroar al 10% HP.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Indeedee remata con Dazzling Gleam; derrota en 2 turnos."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Terrain Priority Collision): Usar movimientos prioritarios en objetivos en el suelo bajo Psychic Terrain resulta en turnos completamente desperdiciados (-1.80 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Fake Out y Grassy Glide fallaron en T1 por Psychic Terrain. Armarouge usó Expanding Force con boost de terreno y Life Orb, barriendo a Rillaboom y dejando a Incineroar al 10% HP. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Indeedee remata con Dazzling Gleam; derrota en 2 turnos."
      },
      {
        "id": "OPT-C",
        "label": "C) Rillaboom Wood Hammer en Armarouge + Incineroar Flare Blitz en Indeedee",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Wood Hammer conecta en Armarouge pero es resistido (-28% HP) y activa Weak Armor (+2 Spe)!",
          "2. Armarouge ahora supera en velocidad a todo tu equipo.",
          "3. Armarouge desata Expanding Force potenciado con STAB y terreno: OHKO a Rillaboom.",
          "4. Incineroar Flare Blitz daña a Indeedee pero queda gravemente herido por el recoil.",
          "5. [PROYECCIÓN TURNO +2]: Rillaboom fainted al recibir Expanding Force + Armor Cannon. Incineroar queda solo contra dos atacantes especiales.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Armarouge conserva Life Orb e Indeedee mantiene Follow Me intacto."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 / Greed): Intentar intercambios de daño directo sin disrumpir el motor de terreno entrega una baja no forzada (-1.65 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Rillaboom fainted al recibir Expanding Force + Armor Cannon. Incineroar queda solo contra dos atacantes especiales. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Armarouge conserva Life Orb e Indeedee mantiene Follow Me intacto."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Rillaboom → Pelipper para cambiar clima + Incineroar Protect",
        "optimal": false,
        "vpDelta": "-1.35 VP",
        "log": [
          "1. Retiras a Rillaboom → Entra Pelipper en seco y activa Drizzle.",
          "2. Armarouge usa Expanding Force en área: bajo Psychic Terrain golpea a ambos rivales independientemente del clima (-72% HP a Pelipper entrante)!",
          "3. Incineroar quema su Protect pasivamente sin aplicar ninguna presión ofensiva.",
          "4. En Turno 2, Pelipper está a 28% HP y el terreno psíquico sigue activo.",
          "5. [PROYECCIÓN TURNO +2]: Doble Protect consumido pasivamente. El rival mantiene control absoluto del campo y prepara un turno de Expanding Force libre.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Retrasas la derrota un turno sin generar ninguna ventaja posicional ni desgaste."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Quemar Protect de forma pasiva sin alterar el estado del tablero agrava la desventaja (-1.35 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Doble Protect consumido pasivamente. El rival mantiene control absoluto del campo y prepara un turno de Expanding Force libre. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Retrasas la derrota un turno sin generar ninguna ventaja posicional ni desgaste."
      }
    ]
  },
  {
    "id": "SC-04",
    "title": "M309 Turno 3: TGT-01 Protect Tunneling vs Incineroar (18% HP) + Rillaboom",
    "driver": "Tunnel_Vision",
    "code": "TGT-01",
    "turnBadge": "TURNO 3 • VP 3v3 • INCINEROAR EN RANGO DE KO",
    "context": "Tienes a Basculegion-M (Swift Swim) y Archaludon en campo. El rival tiene a Incineroar a 18% HP en slot 1 y Rillaboom a 100% HP en slot 2. Incineroar usó Parting Shot el turno previo y acaba de reingresar; la probabilidad de Protect en su slot es superior al 85%.",
    "oppSlots": [
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 18,
        "status": "Protect Obvio"
      },
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 100,
        "status": "Amenaza Wood Hammer"
      }
    ],
    "mySlots": [
      {
        "name": "Basculegion-M",
        "item": "Life Orb",
        "ability": "Swift Swim",
        "hp": 85,
        "status": "Spe 142"
      },
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 90,
        "status": "Spe 105"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Basculegion Wave Crash en Rillaboom + Archaludon Body Press en Rillaboom",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Incineroar usó Protect! Anticipa el remate desesperado.",
          "2. Basculegion redirige su Wave Crash al slot 2 de Rillaboom: ¡conecta por 62% HP!",
          "3. Archaludon ejecuta Body Press en Rillaboom: ¡conecta por 42% HP y logra el OHKO exacto!",
          "4. Rillaboom cae debilitado. En Turno 4 enfrentas a un Incineroar a 18% en 2v1 absoluto.",
          "5. [PROYECCIÓN TURNO +2]: Rillaboom rival debilitado por el foco coordinado. Incineroar usó Protect inútilmente en T1 y ahora está solo frente a dos atacantes.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Basculegion-M y Archaludon eliminan al Incineroar moribundo al inicio del turno siguiente, asegurando victoria 4v2 (+1.65 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): Ignoras el Protect cantado del Pokémon moribundo y castigas al slot activo con daño masivo, eliminando al partner y dejando al rival sin respuestas en T+2.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Rillaboom rival debilitado por el foco coordinado. Incineroar usó Protect inútilmente en T1 y ahora está solo frente a dos atacantes. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Basculegion-M y Archaludon eliminan al Incineroar moribundo al inicio del turno siguiente, asegurando victoria 4v2 (+1.65 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Doble ataque (Wave Crash + Body Press) concentrado en Incineroar",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Incineroar usó Protect!",
          "2. Basculegion Wave Crash se estrella contra la barrera de Protect (0 daño).",
          "3. Archaludon Body Press se estrella contra Protect (0 daño).",
          "4. Rillaboom usa Wood Hammer sobre Basculegion: ¡OHKO crítico y pierdes a tu atacante más veloz!",
          "5. [PROYECCIÓN TURNO +2]: Ambos ataques impactaron en el Protect de Incineroar (0 daño). Rillaboom usó Wood Hammer y noqueó a Basculegion-M.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu principal sweeper físico por túnel de foco sobre un slot de 18% HP."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Protect Tunneling): Atacar al slot obvio con Protect permite al rival castigar severamente a tus aliados (-1.75 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ambos ataques impactaron en el Protect de Incineroar (0 daño). Rillaboom usó Wood Hammer y noqueó a Basculegion-M. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu principal sweeper físico por túnel de foco sobre un slot de 18% HP."
      },
      {
        "id": "OPT-C",
        "label": "C) Basculegion Protect + Archaludon Flash Cannon a Incineroar",
        "optimal": false,
        "vpDelta": "-1.20 VP",
        "log": [
          "1. Basculegion usa Protect. Incineroar usa Protect.",
          "2. Flash Cannon de Archaludon es bloqueado por el Protect de Incineroar.",
          "3. Rillaboom usa High Horsepower sobre Archaludon (-48% HP).",
          "4. Quedas sin tempo y con Archaludon severamente desgastado.",
          "5. [PROYECCIÓN TURNO +2]: Basculegion usó Protect pasivo. Rillaboom atacó libremente a Archaludon desgastando su barra de vida.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes la iniciativa en un turno clave donde podías borrar una pieza rival."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): La pasividad cuando tienes ventaja ofensiva permite al rival recuperar el ritmo (-1.30 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Basculegion usó Protect pasivo. Rillaboom atacó libremente a Archaludon desgastando su barra de vida. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes la iniciativa en un turno clave donde podías borrar una pieza rival."
      },
      {
        "id": "OPT-D",
        "label": "D) Basculegion Last Respects a Incineroar + Archaludon Electro Shot en Rillaboom",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Incineroar usa Protect y anula Last Respects por completo.",
          "2. Archaludon gasta su turno cargando Electro Shot sin lluvia.",
          "3. Rillaboom usa Knock Off sobre Archaludon removiendo sus Leftovers (-35% HP).",
          "4. En Turno 4, Incineroar sigue vivo con Fake Out listo para usar.",
          "5. [PROYECCIÓN TURNO +2]: Basculegion atacó a Incineroar (Protegido) y Archaludon dividió su daño. Rillaboom sobrevive al 40% HP y amenaza Wood Hammer.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Falta de daño concentrado permite al rival mantener dos atacantes en mesa."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Inefficient Targeting): Dividir daño entre un slot protegido y uno con vida completa pierde el KO limpio (-1.40 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Basculegion atacó a Incineroar (Protegido) y Archaludon dividió su daño. Rillaboom sobrevive al 40% HP y amenaza Wood Hammer. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Falta de daño concentrado permite al rival mantener dos atacantes en mesa."
      }
    ]
  },
  {
    "id": "SC-05",
    "title": "M314 Turno 2: TGT-02 Spread Redirection Error vs Maushold Follow Me + Annihilape",
    "driver": "Tunnel_Vision",
    "code": "TGT-02",
    "turnBadge": "TURNO 2 • SEÑUELO ACTIVO • VP 4v4",
    "context": "Enfrentas Maushold + Annihilape. Annihilape tiene +1 Atk tras Bulk Up en Turno 1. Cuentas con Primarina (Hyper Voice) y Archaludon. Maushold amenaza Follow Me para absorber cualquier ataque dirigido a Annihilape.",
    "oppSlots": [
      {
        "name": "Maushold",
        "item": "Focus Sash",
        "ability": "Friend Guard",
        "hp": 100,
        "status": "Follow Me Ready"
      },
      {
        "name": "Annihilape",
        "item": "Leftovers",
        "ability": "Defiant",
        "hp": 100,
        "status": "+1 Atk / +1 Def"
      }
    ],
    "mySlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 100,
        "status": "Hyper Voice Ready"
      },
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 100,
        "status": "Dragon Pulse Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Primarina Hyper Voice + Archaludon Dragon Pulse en slot Annihilape",
        "optimal": true,
        "vpDelta": "+1.80 VP",
        "log": [
          "1. Maushold usa Follow Me!",
          "2. Primarina desata Hyper Voice de área: ¡ignora la redirección y golpea a ambos rivales!",
          "3. Maushold recibe 64% HP y pierde su Focus Sash; Annihilape recibe 48% HP y Mystic Water potencia el daño de Hyper Voice.",
          "4. Archaludon Dragon Pulse es redirigido a Maushold y lo noquea (0% HP). Annihilape queda solo sin señuelo.",
          "5. [PROYECCIÓN TURNO +2]: Hyper Voice (Spread de Sonido) traspasó Follow Me e impactó a ambos rivales. Maushold rompió Focus Sash (1 HP) y Annihilape recibió 45% HP.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: En T+2 Archaludon y Primarina rematan a Maushold y controlan el Rage Fist de Annihilape antes de que acumule cargas (+1.70 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Los ataques de propagación ignoran Follow Me / Rage Powder. Aplicas daño simultáneo a la pieza de soporte y al sweeper sin regalar cargas de Rage Fist.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Hyper Voice (Spread de Sonido) traspasó Follow Me e impactó a ambos rivales. Maushold rompió Focus Sash (1 HP) y Annihilape recibió 45% HP. • 6. [PROYECCIÓN TURNO +3 / WINCON]: En T+2 Archaludon y Primarina rematan a Maushold y controlan el Rage Fist de Annihilape antes de que acumule cargas (+1.70 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Dual Single-Target Moonblast + Body Press dirigidos a Annihilape",
        "optimal": false,
        "vpDelta": "-1.70 VP",
        "log": [
          "1. Maushold usa Follow Me!",
          "2. Primarina Moonblast es redirigido a Maushold y activa su Focus Sash (1 HP).",
          "3. Archaludon Body Press es redirigido a Maushold (0 daño residual tras Sash).",
          "4. Annihilape queda 100% ileso y desata Drain Punch demoledor (+2 Atk Rage Fist listo).",
          "5. [PROYECCIÓN TURNO +2]: Moonblast y Flash Cannon fueron redirigidos a Maushold. Annihilape usó Bulk Up libremente sin recibir daño.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Con +1 Atk/+1 Def y Rage Fist preparado, Annihilape se vuelve imposible de frenar en T+3."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-02 Spread Redirection Error): Dirigir ataques de un solo objetivo contra redirección mientras el sweeper se setea condena la partida (-1.70 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Moonblast y Flash Cannon fueron redirigidos a Maushold. Annihilape usó Bulk Up libremente sin recibir daño. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Con +1 Atk/+1 Def y Rage Fist preparado, Annihilape se vuelve imposible de frenar en T+3."
      },
      {
        "id": "OPT-C",
        "label": "C) Doble Protect pasivo esperando que Maushold gaste Follow Me",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Primarina usa Protect. Archaludon usa Protect.",
          "2. Maushold usa Super Fang sobre el Protect (bloqueado).",
          "3. Annihilape aprovecha el turno libre para usar otro Bulk Up (+2 Atk / +2 Def).",
          "4. En Turno 3, Annihilape es imparable con Rage Fist cargado.",
          "5. [PROYECCIÓN TURNO +2]: Primarina usó Protect. Maushold redirigió el único ataque de Archaludon. Annihilape atacó con Drain Punch recuperando salud.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes tempo ofensivo permitiendo la consolidación del núcleo rival."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): No aprovechar la opción de spread move cuando el rival gasta su turno de redirección es un error grave (-1.35 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Primarina usó Protect. Maushold redirigió el único ataque de Archaludon. Annihilape atacó con Drain Punch recuperando salud. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes tempo ofensivo permitiendo la consolidación del núcleo rival."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar de ambos slots para traer Intimidate de Incineroar",
        "optimal": false,
        "vpDelta": "-1.55 VP",
        "log": [
          "1. Cambias tus dos slots en seco trayendo a Incineroar.",
          "2. Incineroar activa Intimidate... ¡Annihilape tiene habilidad Defiant!",
          "3. ¡El Ataque de Annihilape sube 2 niveles (+3 Atk total) en lugar de bajar!",
          "4. Annihilape usa Close Combat y destruye a Incineroar de un solo impacto.",
          "5. [PROYECCIÓN TURNO +2]: Ambos aliados atacaron a Annihilape con ataques individuales que fueron desviados a Maushold, dejándolo a 1 HP pero intacto de cara a un segundo Follow Me.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Annihilape barre en el turno siguiente con Drain Punch sobre Archaludon."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-02 Redirection Tunneling): Caer en la trampa de redirección sin spread moves entrega el control del match (-1.60 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ambos aliados atacaron a Annihilape con ataques individuales que fueron desviados a Maushold, dejándolo a 1 HP pero intacto de cara a un segundo Follow Me. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Annihilape barre en el turno siguiente con Drain Punch sobre Archaludon."
      }
    ]
  },
  {
    "id": "SC-06",
    "title": "M318 Turno 4: TGT-03 Damage Overkill vs Primarina (12% HP) + Kingambit",
    "driver": "Tunnel_Vision",
    "code": "TGT-03",
    "turnBadge": "TURNO 4 • VP 2v2 • RECURSOS CRÍTICOS",
    "context": "Primarina rival está a 12% HP en slot 1. Kingambit sano a 100% HP en slot 2 con Swords Dance. Dispones de Rillaboom (Grassy Glide) e Incineroar (Will-O-Wisp / Flare Blitz). El Grassy Terrain está activo.",
    "oppSlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 12,
        "status": "En Rango KO"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 100,
        "status": "Swords Dance Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 80,
        "status": "Glide Priority"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 75,
        "status": "Will-O-Wisp Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Grassy Glide en Primarina + Incineroar Will-O-Wisp en Kingambit",
        "optimal": true,
        "vpDelta": "+1.90 VP",
        "log": [
          "1. Grassy Glide (Prioridad en Grassy Terrain) conecta antes que cualquier movimiento y elimina a Primarina (0% HP) con un solo slot.",
          "2. Kingambit intenta Kowtow Cleave pero Incineroar resiste el golpe (-32% HP).",
          "3. Incineroar quema a Kingambit con Will-O-Wisp, neutralizando su daño físico a la mitad de forma permanente!",
          "4. Aseguras el KO del slot débil y desarmas por completo la condición de victoria de Kingambit.",
          "5. [PROYECCIÓN TURNO +2]: Kingambit recibió Close Combat de Incineroar (-75% HP) y Wood Hammer de Rillaboom, cayendo debilitado. Primarina a 12% HP no puede remontar sola 1v4.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Rillaboom remata a Primarina con Grassy Glide prioritario en el siguiente turno (+1.60 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.60 VP): Concentrar recursos en neutralizar la amenaza activa más peligrosa (Kingambit) mientras dejas al slot moribundo sin impacto real en el tablero asegura la victoria.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Kingambit recibió Close Combat de Incineroar (-75% HP) y Wood Hammer de Rillaboom, cayendo debilitado. Primarina a 12% HP no puede remontar sola 1v4. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Rillaboom remata a Primarina con Grassy Glide prioritario en el siguiente turno (+1.60 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Doble ataque masivo (Wood Hammer + Flare Blitz) enfocado en Primarina",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Wood Hammer noquea a Primarina de inmediato con recoil excesivo.",
          "2. Flare Blitz se convierte en Overkill contra un objetivo que ya no está en campo.",
          "3. Kingambit usa Swords Dance gratis (+2 Atk) sin recibir daño ni quemadura!",
          "4. En Turno 5, Kingambit desata Sucker Punch potenciado y barre a tu equipo restante.",
          "5. [PROYECCIÓN TURNO +2]: Ambos aliados atacaron a Primarina (12% HP), causando overkill masivo. Kingambit ejecutó Kowtow Cleave con Black Glasses y fulminó a Incineroar.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Kingambit activa Defiant / Sucker Punch y barre a Rillaboom en T+3."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Damage Overkill): Gastar dos acciones completas para eliminar 12% de vida permite al rival noquear a tu pieza clave (-1.65 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ambos aliados atacaron a Primarina (12% HP), causando overkill masivo. Kingambit ejecutó Kowtow Cleave con Black Glasses y fulminó a Incineroar. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Kingambit activa Defiant / Sucker Punch y barre a Rillaboom en T+3."
      },
      {
        "id": "OPT-C",
        "label": "C) Doble ataque concentrado en Kingambit ignorando el 12% HP de Primarina",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Atacas a Kingambit con Wood Hammer y Flare Blitz dejándolo en 35% HP.",
          "2. Kingambit usa Sucker Punch sobre Rillaboom (-50% HP).",
          "3. Primarina sobrevive a 12% y lanza Moonblast crítico sobre Incineroar debilitándolo por completo (0% HP)!",
          "4. Dejas vivo a un atacante especial peligroso por no rematarlo con prioridad.",
          "5. [PROYECCIÓN TURNO +2]: Rillaboom Protect y Incineroar atacó solo a Kingambit (sobrevive con 30% HP). Primarina atacó con Moonblast a Incineroar.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Ambos rivales sobreviven y mantienen doble presión ofensiva."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Dividir la presión ofensiva permite al rival estabilizarse (-1.30 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Rillaboom Protect y Incineroar atacó solo a Kingambit (sobrevive con 30% HP). Primarina atacó con Moonblast a Incineroar. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Ambos rivales sobreviven y mantienen doble presión ofensiva."
      },
      {
        "id": "OPT-D",
        "label": "D) Rillaboom Protect + Incineroar Parting Shot en Primarina",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Rillaboom usa Protect.",
          "2. Incineroar usa Parting Shot en Primarina; Primarina cambia o resiste.",
          "3. Kingambit usa Kowtow Cleave demoledor sobre Incineroar.",
          "4. Gastas tempo en reducir estadísticas de un Pokémon que debió morir este turno.",
          "5. [PROYECCIÓN TURNO +2]: Ataques sin foco coordinado dejaron a ambos rivales con vida (Primarina a 2% HP y Kingambit al 45% HP).",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Kingambit y Primarina conectan doble ataque y debilitan a Incineroar."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Inefficient Focus): Falta de cálculo de daño exacto regala turnos extra al rival (-1.45 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ataques sin foco coordinado dejaron a ambos rivales con vida (Primarina a 2% HP y Kingambit al 45% HP). • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Kingambit y Primarina conectan doble ataque y debilitan a Incineroar."
      }
    ]
  },
  {
    "id": "SC-07",
    "title": "M316 Turno 4: POS-03 Passive Protect abajo en Equidad vs Trick Room (1T restante)",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 4 • TRICK ROOM 1 TURNO • VP 2v3 DESVENTAJA",
    "context": "Estás abajo 2v3 en piezas vivas. Trick Room está en su último turno (expira al final de este turno). El rival tiene a Torkoal y Armarouge en campo. Si usas Protect pasivo en ambos slots, el rival simplemente reseteará Trick Room o meterá setup gratis.",
    "oppSlots": [
      {
        "name": "Armarouge",
        "item": "Life Orb",
        "ability": "Flash Fire",
        "hp": 65,
        "status": "Expanding Force"
      },
      {
        "name": "Indeedee-F",
        "item": "Psychic Seed",
        "ability": "Psychic Surge",
        "hp": 40,
        "status": "Trick Room Setter"
      }
    ],
    "mySlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 75,
        "status": "Spe 169"
      },
      {
        "name": "Rotom-Wash",
        "item": "Sitrus Berry",
        "ability": "Levitate",
        "hp": 60,
        "status": "Spe 115"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Doble ofensiva directa (Hydro Pump Armarouge + Stomping Tantrum Indeedee)",
        "optimal": true,
        "vpDelta": "+1.50 VP",
        "log": [
          "1. Hydro Pump conecta en Armarouge y lo noquea (0% HP) antes de que pueda atacar!",
          "2. Indeedee intenta usar Dazzling Gleam pero Stomping Tantrum de Garchomp la noquea de inmediato.",
          "3. Trick Room expira al final del turno!",
          "4. En Turno 5 tus Pokémon recuperan la iniciativa absoluta de velocidad y el rival se queda sin atacantes.",
          "5. [PROYECCIÓN TURNO +2]: Trick Room expira al final del turno. Garchomp (169 Spe) y Rotom-Wash (115 Spe) recuperan la iniciativa absoluta sobre Armarouge e Indeedee.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Doble ataque rápido en dimensiones normales barre al equipo rival sin que puedan volver a colocar Trick Room (+1.75 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Reconocer el último turno de Trick Room y ejecutar la jugada de transición óptima permite retomar la iniciativa inmediatamente al recuperar la velocidad normal.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Trick Room expira al final del turno. Garchomp (169 Spe) y Rotom-Wash (115 Spe) recuperan la iniciativa absoluta sobre Armarouge e Indeedee. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Doble ataque rápido en dimensiones normales barre al equipo rival sin que puedan volver a colocar Trick Room (+1.75 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Doble Protect pasivo para esperar a que expire Trick Room sin recibir daño",
        "optimal": false,
        "vpDelta": "-1.65 VP",
        "log": [
          "1. Garchomp usa Protect. Rotom-Wash usa Protect.",
          "2. El rival lee el doble Protect pasivo y no ataca: ¡Indeedee vuelve a castear Trick Room con éxito!",
          "3. Armarouge usa Calm Mind (+1 SpA / +1 SpD) gratis.",
          "4. En Turno 5, Trick Room reinicia a 5 turnos y quedas acorralado sin opciones.",
          "5. [PROYECCIÓN TURNO +2]: Ambos aliados usaron Protect pasivo en el último turno de TR. Indeedee reinició Trick Room libremente!",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Otros 5 turnos de Trick Room activo con tu equipo en desventaja de velocidad; derrota segura."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Quemar Protect cuando el rival va a resetear Trick Room garantiza que mantenga el control del tempo (-1.80 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ambos aliados usaron Protect pasivo en el último turno de TR. Indeedee reinició Trick Room libremente! • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Otros 5 turnos de Trick Room activo con tu equipo en desventaja de velocidad; derrota segura."
      },
      {
        "id": "OPT-C",
        "label": "C) Cambiar Garchomp → Corviknight + Rotom-Wash Thunderbolt",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Retiras a Garchomp → Entra Corviknight en seco.",
          "2. Armarouge usa Armor Cannon sobre el slot entrante de Corviknight: ¡OHKO masivo con debilidad de Fuego!",
          "3. Rotom-Wash queda solo contra dos atacantes psíquicos.",
          "4. Tu desventaja pasa de 2v3 a 1v3 irreversible.",
          "5. [PROYECCIÓN TURNO +2]: Garchomp atacó bajo TR y fue superado en velocidad por Armarouge, recibiendo Expanding Force masivo.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu atacante principal justo antes de que el campo vuelva a la normalidad."
        ],
        "verdict": "❌ FUGA TÁCTICA (SPD-01 Speed Miscalculation): Atacar sin cobertura en el último turno de Trick Room expone a tus piezas rápidas a daño gratuito (-1.50 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Garchomp atacó bajo TR y fue superado en velocidad por Armarouge, recibiendo Expanding Force masivo. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu atacante principal justo antes de que el campo vuelva a la normalidad."
      },
      {
        "id": "OPT-D",
        "label": "D) Rotom-Wash Will-O-Wisp + Garchomp Swords Dance",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Will-O-Wisp falla en Armarouge debido a Flash Fire (¡absorbe el fuego y potencia sus ataques especiales!)",
          "2. Armarouge desata Expanding Force potenciado y noquea a Garchomp mientras baila Swords Dance.",
          "3. Pierdes a tu atacante físico por buscar un boost en lugar de atacar.",
          "5. [PROYECCIÓN TURNO +2]: Switch seco de Rotom-Wash recibió daño innecesario de Dazzling Gleam. El rival mantiene la iniciativa.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes el control del tablero por un cambio desalineado con la expiración de TR."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar sin posicionamiento ofensivo en turno de expiración de campo regala tempo (-1.40 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Switch seco de Rotom-Wash recibió daño innecesario de Dazzling Gleam. El rival mantiene la iniciativa. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes el control del tablero por un cambio desalineado con la expiración de TR."
      }
    ]
  },
  {
    "id": "SC-08",
    "title": "M319 Turno 3: MEC-01 & MEC-02 Prioridad en Psychic Terrain (Pelipper Airborne vs Sneasler)",
    "driver": "Greed",
    "code": "MEC-01",
    "turnBadge": "TURNO 3 • PSYCHIC TERRAIN ACTIVO • VP 3v3",
    "context": "Hay Psychic Terrain activo en el campo. Tienes a Pelipper (tipo Volador / Levitate) y Archaludon en campo frente a Sneasler e Incineroar. Un error común es asumir que Pelipper está protegido contra Fake Out o Sucker Punch por el terreno psíquico.",
    "oppSlots": [
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 100,
        "status": "Fake Out Ready"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 85,
        "status": "Knock Off Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 85,
        "status": "Airborne (Volador)"
      },
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 90,
        "status": "Grounded (Suelo)"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Pelipper Protect + Archaludon Electro Shot en Sneasler",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Pelipper usa Protect! Como es tipo Volador, NO está protegido por Psychic Terrain contra prioridad.",
          "2. Sneasler intenta Fake Out sobre Pelipper: ¡choca contra el Protect y gasta su turno!",
          "3. Archaludon desata Electro Shot en 1 turno bajo lluvia sobre Sneasler: activa su Focus Sash (1 HP).",
          "4. Mantienes la salud intacta de tu setter de clima y desgastas al sweeper rival.",
          "5. [PROYECCIÓN TURNO +2]: Pelipper es de tipo Volador (Airborne) y NO está protegido por Psychic Terrain contra movimientos de prioridad del rival. Al posicionar a Archaludon y atacar con Pelipper Weather Ball en Lluvia, aseguras KO en Incineroar.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Lluvia activa y Archaludon con Stamina garantizan checkmate sobre Sneasler en T+3 (+1.60 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.60 VP): Demuestras dominio absoluto de la regla de exención aérea de terreno: los Pokémon voladores no tienen inmunidad a prioridad en Terreno Psíquico, por lo que jugar ofensivo sin falsas seguridades es la línea ganadora.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Pelipper es de tipo Volador (Airborne) y NO está protegido por Psychic Terrain contra movimientos de prioridad del rival. Al posicionar a Archaludon y atacar con Pelipper Weather Ball en Lluvia, aseguras KO en Incineroar. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Lluvia activa y Archaludon con Stamina garantizan checkmate sobre Sneasler en T+3 (+1.60 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Pelipper Hurricane a Sneasler sin proteger confiando en el Terreno Psíquico",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Sneasler usa Fake Out sobre Pelipper... ¡Y CONECTA exitosamente!",
          "2. Como Pelipper es Volador, no toca el suelo y no recibe la inmunidad a prioridad.",
          "3. Pelipper retrocede y pierde su turno por completo.",
          "4. Incineroar Knock Off asesta golpe demoledor sobre Pelipper despojando su objeto.",
          "5. [PROYECCIÓN TURNO +2]: Confiando en que Psychic Terrain protegía a Pelipper, no protegiste. Sneasler usó Fake Out / Feint y debilitó a Pelipper antes de atacar.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu setter de lluvia por ignorar la exención aérea de terreno."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-02 Airborne Ground Exemption): Creer que los Pokémon voladores están protegidos por Terreno Psíquico contra prioridad es un error crítico de mecánicas (-1.75 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Confiando en que Psychic Terrain protegía a Pelipper, no protegiste. Sneasler usó Fake Out / Feint y debilitó a Pelipper antes de atacar. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu setter de lluvia por ignorar la exención aérea de terreno."
      },
      {
        "id": "OPT-C",
        "label": "C) Intentar usar un movimiento de prioridad con Archaludon hacia Sneasler",
        "optimal": false,
        "vpDelta": "-1.70 VP",
        "log": [
          "1. Tu ataque prioritario falla de inmediato porque Sneasler está tocando el suelo en Psychic Terrain.",
          "2. Sneasler usa Close Combat sobre Archaludon infligiendo daño masivo.",
          "3. Desperdicias la acción ofensiva por colisión de prioridad.",
          "5. [PROYECCIÓN TURNO +2]: Archaludon usó Protect pasivo mientras Pelipper recibía daño masivo de Close Combat de Sneasler.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida de presencia de lluvia y colapso de la estructura defensiva."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): La falta de coordinación entre slots ante amenazas mixtas destruye la sinergia de equipo (-1.45 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Archaludon usó Protect pasivo mientras Pelipper recibía daño masivo de Close Combat de Sneasler. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida de presencia de lluvia y colapso de la estructura defensiva."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar de Archaludon a Rillaboom para sobreescribir el terreno",
        "optimal": false,
        "vpDelta": "-1.35 VP",
        "log": [
          "1. Retiras a Archaludon → Entra Rillaboom en seco.",
          "2. Rillaboom activa Grassy Surge, pero recibe Close Combat de Sneasler al entrar: ¡pierde el 82% de salud!",
          "3. Tu pivot queda en rango de KO para cualquier ataque posterior.",
          "5. [PROYECCIÓN TURNO +2]: Ataques sin prioridad fallaron en conectar por mala predicción de Protect rival.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Sneasler activa Unburden y barre en el siguiente turno."
        ],
        "verdict": "❌ FUGA TÁCTICA (Autopilot / Greed): No asegurar el KO del slot más amenazante permite la activación de Unburden (-1.55 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ataques sin prioridad fallaron en conectar por mala predicción de Protect rival. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Sneasler activa Unburden y barre en el siguiente turno."
      }
    ]
  },
  {
    "id": "SC-09",
    "title": "M320 Turno 1: SPD-01 Escalado Instantáneo de Velocidad Mega (Lucario-Mega vs Garchomp)",
    "driver": "Greed",
    "code": "SPD-01",
    "turnBadge": "TURNO 1 • VP 4v4 • ESCALADO INSTANTÁNEO",
    "context": "Tienes a Lucario (Spe base 90) frente a Garchomp (Spe base 102). En Regulation M-C, la Mega Evolución a Lucario-Mega (Spe base 112) recalcula la velocidad instantáneamente en el mismo turno de activación.",
    "oppSlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Spe 169 (Base 102)"
      },
      {
        "name": "Rotom-Wash",
        "item": "Sitrus Berry",
        "ability": "Levitate",
        "hp": 100,
        "status": "Spe 115"
      }
    ],
    "mySlots": [
      {
        "name": "Lucario",
        "item": "Lucarionite",
        "ability": "Inner Focus",
        "hp": 100,
        "status": "Mega Ready (Spe 180)"
      },
      {
        "name": "Whimsicott",
        "item": "Mental Herb",
        "ability": "Prankster",
        "hp": 100,
        "status": "Tailwind Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Mega Evolucionar a Lucario-Mega y ejecutar Flash Cannon / Close Combat directo",
        "optimal": true,
        "vpDelta": "+1.85 VP",
        "log": [
          "1. Lucario Mega Evoluciona! Su Speed Tier se actualiza al instante a 112 Base Spe (180 Spe Nivel 50).",
          "2. Lucario supera en velocidad a Garchomp (169 Spe) sin depender de Tailwind!",
          "3. Lucario desata Close Combat con Adaptability: ¡OHKO masivo sobre Garchomp antes de que ataque!",
          "4. Whimsicott usa Moonblast sobre Rotom-Wash desgastando su slot.",
          "5. [PROYECCIÓN TURNO +2]: Lucario Mega Evoluciona y su velocidad pasa instantáneamente a 180 Spe (superando los 169 Spe de Garchomp). Conecta Close Combat antes de que Garchomp se mueva y logra el OHKO limpio.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Whimsicott coloca Tailwind; Lucario-Mega domina a Rotom-Wash en T+3 para cerrar el match (+1.80 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.80 VP): En Pokémon Champions la Mega Evolución recalcula la velocidad en el acto (Activation Phase). Lucario-Mega adelanta a Garchomp de inmediato y lo elimina antes de que pueda tocar el campo.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Lucario Mega Evoluciona y su velocidad pasa instantáneamente a 180 Spe (superando los 169 Spe de Garchomp). Conecta Close Combat antes de que Garchomp se mueva y logra el OHKO limpio. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Whimsicott coloca Tailwind; Lucario-Mega domina a Rotom-Wash en T+3 para cerrar el match (+1.80 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Usar Protect con Lucario por miedo a que Garchomp sea más rápido (mecánica antigua)",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Lucario usa Protect creyendo erróneamente que la velocidad no se actualiza hasta el turno siguiente.",
          "2. Garchomp usa Swords Dance libremente (+2 Atk) sin recibir ningún castigo.",
          "3. Rotom-Wash usa Thunderbolt sobre Whimsicott (-55% HP).",
          "4. En Turno 2, Garchomp tiene +2 en Ataque y amenaza con barrer el campo.",
          "5. [PROYECCIÓN TURNO +2]: Asumiendo erróneamente que la velocidad no cambiaba en el turno de Mega, Lucario usó Protect innecesario. Garchomp usó Earthquake y rompió el Focus Sash de Whimsicott.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: En T+2 Garchomp predice el Protect y presiona con Swords Dance o Earthquake."
        ],
        "verdict": "❌ FUGA TÁCTICA (SPD-01 Activation Phase Blindness): Desconocer el escalado instantáneo de velocidad de la Mega Evolución regala un turno ofensivo de oro (-1.70 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Asumiendo erróneamente que la velocidad no cambiaba en el turno de Mega, Lucario usó Protect innecesario. Garchomp usó Earthquake y rompió el Focus Sash de Whimsicott. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: En T+2 Garchomp predice el Protect y presiona con Swords Dance o Earthquake."
      },
      {
        "id": "OPT-C",
        "label": "C) No Mega Evolucionar este turno y hacer Swords Dance con Lucario base",
        "optimal": false,
        "vpDelta": "-1.90 VP",
        "log": [
          "1. Lucario permanece en su forma base (Spe 90).",
          "2. Garchomp (Spe 102) se mueve primero y usa Earthquake con Life Orb: ¡OHKO directo (0% HP) a Lucario!",
          "3. Lucario cae debilitado sin haber evolucionado ni ejecutado su acción.",
          "4. Tu atacante Mega queda eliminado en Turno 1.",
          "5. [PROYECCIÓN TURNO +2]: Lucario atacó sin Mega Evolucionar (Spe 112 base). Garchomp (169 Spe) actuó primero y ejecutó Earthquake: OHKO a Lucario y daño masivo a Whimsicott.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida de la Mega sin haber ejecutado una sola acción ofensiva."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Failure to Mega Evolve): Olvidar activar la Mega Evolución condena a tu atacante a ser superado en velocidad y eliminado (-1.85 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Lucario atacó sin Mega Evolucionar (Spe 112 base). Garchomp (169 Spe) actuó primero y ejecutó Earthquake: OHKO a Lucario y daño masivo a Whimsicott. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida de la Mega sin haber ejecutado una sola acción ofensiva."
      },
      {
        "id": "OPT-D",
        "label": "D) Hard switch de Lucario a un compañero de tipo Volador en seco",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Retiras a Lucario → Entra Pelipper en seco.",
          "2. Garchomp anticipa el cambio de tipo volador y lanza Stone Edge crítico: ¡OHKO a Pelipper entrante!",
          "3. Regalas una pieza sin haber disputado la velocidad.",
          "5. [PROYECCIÓN TURNO +2]: Whimsicott atacó en vez de apoyar y Garchomp castigó con Rock Slide causando flinch.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida total del ritmo de combate por desaprovechar la ventaja de velocidad."
        ],
        "verdict": "❌ FUGA TÁCTICA (Autopilot / Greed): No priorizar la eliminación de Garchomp cuando tienes la ventaja de velocidad garantizada es un error grave (-1.50 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Whimsicott atacó en vez de apoyar y Garchomp castigó con Rock Slide causando flinch. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida total del ritmo de combate por desaprovechar la ventaja de velocidad."
      }
    ]
  },
  {
    "id": "SC-10",
    "title": "M321 Turno 3: Format Divergence (Charizard-Mega-Y expuesto a Prioridad en Terreno Psíquico)",
    "driver": "Format_Divergence",
    "code": "MEC-02",
    "turnBadge": "TURNO 3 • PSYCHIC TERRAIN ACTIVO • VP 3v3",
    "context": "Tienes a Charizard-Mega-Y en campo bajo Psychic Terrain. Enfrentas a Rillaboom (Grassy Glide) y Kingambit (Sucker Punch). El entrenador cree falsamente que el terreno psíquico anula la prioridad contra su Mega Volador.",
    "oppSlots": [
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 80,
        "status": "Grassy Glide Ready"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 85,
        "status": "Sucker Punch Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Charizard-Mega-Y",
        "item": "Charizardite Y",
        "ability": "Drought",
        "hp": 45,
        "status": "Airborne (Volador)"
      },
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 70,
        "status": "Armor Tail Activo"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard-Mega-Y Protect + Farigiraf Hyper Voice",
        "optimal": true,
        "vpDelta": "+1.80 VP",
        "log": [
          "1. Charizard usa Protect! Se resguarda ante cualquier agresión.",
          "2. Rillaboom intenta Grassy Glide sobre Charizard: ¡el ataque impacta en la barrera de Protect!",
          "3. Si Charizard no hubiera protegido, habría caído porque al volar NO tiene protección de terreno.",
          "4. Farigiraf Hyper Voice conecta en ambos rivales (-35% HP a cada uno).",
          "5. [PROYECCIÓN TURNO +2]: Charizard-Mega-Y es tipo Fuego/Volador (Airborne). Farigiraf en campo con Armor Tail bloquea Sucker Punch de Kingambit y Grassy Glide de Rillaboom. Charizard ejecuta Heat Wave en Sol eliminando a ambos rivales.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Doble KO limpio con Sol activo y Farigiraf intacto (+1.75 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Armor Tail de Farigiraf protege a todo tu bando de ataques con prioridad, permitiendo a Charizard-Mega-Y disparar su ataque de propagación en Sol con absoluta impunidad.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Charizard-Mega-Y es tipo Fuego/Volador (Airborne). Farigiraf en campo con Armor Tail bloquea Sucker Punch de Kingambit y Grassy Glide de Rillaboom. Charizard ejecuta Heat Wave en Sol eliminando a ambos rivales. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Doble KO limpio con Sol activo y Farigiraf intacto (+1.75 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Charizard Heat Wave sin proteger asumiendo inmunidad a prioridad",
        "optimal": false,
        "vpDelta": "-1.90 VP",
        "log": [
          "1. Rillaboom ejecuta Grassy Glide sobre Charizard: al ser tipo Volador, ¡el ataque prioritario CONECTA!",
          "2. Charizard recibe 38% HP y queda al borde del desmayo.",
          "3. Kingambit ejecuta Sucker Punch sobre Charizard: ¡OHKO antes de poder lanzar Heat Wave!",
          "4. Pierdes a tu Mega atacante por malinterpretar la mecánica de terreno.",
          "5. [PROYECCIÓN TURNO +2]: Charizard usó Protect creyendo que Armor Tail no cubría a voladores. Farigiraf recibió Knock Off de Kingambit (-65% HP).",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes un turno de sol gratuito permitiendo al rival debilitar a Farigiraf en T+2."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): La desconfianza en las habilidades aliadas genera pasividad innecesaria (-1.40 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Charizard usó Protect creyendo que Armor Tail no cubría a voladores. Farigiraf recibió Knock Off de Kingambit (-65% HP). • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes un turno de sol gratuito permitiendo al rival debilitar a Farigiraf en T+2."
      },
      {
        "id": "OPT-C",
        "label": "C) Cambiar a Charizard por Ursaluna en la banca",
        "optimal": false,
        "vpDelta": "-2.50 VP",
        "log": [
          "1. Intento de switch a especie Ursaluna...",
          "2. [ILLEGAL_FORMAT_SPECIES]: Ursaluna no forma parte de la lista permitida de Regulation M-C.",
          "3. Descalificación inmediata o turno anulado por infracción de formato.",
          "5. [PROYECCIÓN TURNO +2]: Cambiaste a Farigiraf perdiendo Armor Tail. Kingambit conectó Sucker Punch y Rillaboom Grassy Glide sobre Charizard-Mega-Y, debilitándolo de inmediato.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida de tu Mega por retirar la protección contra prioridad."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Retirar la pieza de soporte que previene la prioridad rival condena a tu atacante frágil (-1.80 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Cambiaste a Farigiraf perdiendo Armor Tail. Kingambit conectó Sucker Punch y Rillaboom Grassy Glide sobre Charizard-Mega-Y, debilitándolo de inmediato. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pérdida de tu Mega por retirar la protección contra prioridad."
      },
      {
        "id": "OPT-D",
        "label": "D) Charizard usa Roost para intentar curarse en Turno 3",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Charizard usa Roost y recupera 50% HP, pero pierde su tipo Volador durante el turno.",
          "2. Kingambit usa Kowtow Cleave con Black Glasses: daño masivo (-60% HP).",
          "3. Quedas sin aplicar daño y bajo la misma presión ofensiva.",
          "5. [PROYECCIÓN TURNO +2]: Ataque individual a Kingambit permitió a Rillaboom conectar Knock Off en Farigiraf y despojar su Mental Herb.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Daño insuficiente para sellar la partida en un turno."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Inefficient Spread Usage): Usar ataques individuales cuando el spread move en Sol asegura doble KO es subóptimo (-1.50 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ataque individual a Kingambit permitió a Rillaboom conectar Knock Off en Farigiraf y despojar su Mental Herb. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Daño insuficiente para sellar la partida en un turno."
      }
    ]
  },
  {
    "id": "SC-11",
    "title": "M322 Turno 2: Greed de Boost (+2 Nasty Plot) vs Asegurar KO Directo sobre Basculegion",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 2 • LLUVIA ACTIVA • VP 3v3",
    "context": "Tienes a Raichu-Mega-X frente a Basculegion-M rival (80% HP) en Lluvia activa. Puedes asegurar el KO con Thunderbolt potenciado o caer en la tentación de meter Nasty Plot (+2 SpA) para buscar un 4-0 sweep.",
    "oppSlots": [
      {
        "name": "Basculegion-M",
        "item": "Life Orb",
        "ability": "Swift Swim",
        "hp": 80,
        "status": "Swift Swim / Wave Crash"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 60,
        "status": "Rain 4T"
      }
    ],
    "mySlots": [
      {
        "name": "Raichu-Mega-X",
        "item": "Raichunite X",
        "ability": "Lightning Rod",
        "hp": 100,
        "status": "Spe 178"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 80,
        "status": "Fake Out Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Raichu Thunderbolt directo a Basculegion + Incineroar Fake Out a Pelipper",
        "optimal": true,
        "vpDelta": "+1.95 VP",
        "log": [
          "1. Incineroar usa Fake Out sobre Pelipper y lo hace retroceder.",
          "2. Raichu-Mega-X desata Thunderbolt con STAB super efectivo sobre Basculegion: ¡108% HP de daño garantizado!",
          "3. Basculegion cae debilitado (0% HP) antes de poder lanzar su devastador Wave Crash en lluvia.",
          "4. Desarmas el núcleo de lluvia del rival con cero daño recibido.",
          "5. [PROYECCIÓN TURNO +2]: Raichu-Mega-X asegura el KO inmediato sobre Basculegion-M con Volt Tackle / Thunderbolt antes de que ejecute Wave Crash bajo lluvia. Incineroar usa Knock Off sobre Pelipper.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Eliminado el principal sweeper acuático, el resto del equipo rival no puede quebrar la estructura de Incineroar y Raichu (+1.70 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Asegurar el KO directo sobre la mayor amenaza ofensiva en lugar de buscar codiciosos turnos de setup garantiza el wincon sin riesgo de ser noqueado.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Raichu-Mega-X asegura el KO inmediato sobre Basculegion-M con Volt Tackle / Thunderbolt antes de que ejecute Wave Crash bajo lluvia. Incineroar usa Knock Off sobre Pelipper. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Eliminado el principal sweeper acuático, el resto del equipo rival no puede quebrar la estructura de Incineroar y Raichu (+1.70 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Raichu usa Nasty Plot (+2 SpA) buscando el sweep completo de 4 KOs",
        "optimal": false,
        "vpDelta": "-2.10 VP",
        "log": [
          "1. Incineroar usa Fake Out en Pelipper.",
          "2. Raichu usa Nasty Plot: ¡su Ataque Especial sube 2 niveles!",
          "3. Basculegion bajo Swift Swim se mueve antes de que puedas capitalizar y desata Wave Crash en Lluvia: ¡OHKO letal a Raichu (0% HP)!",
          "4. Pierdes a tu Mega sweeper con 0 KOs ejecutados por avaricia de estadísticas.",
          "5. [PROYECCIÓN TURNO +2]: Raichu usó Nasty Plot para quedar a +2 SpA. Basculegion-M bajo lluvia desató Wave Crash potenciado: ¡OHKO masivo sobre Raichu-Mega-X!",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Quedas con un boost inútil en un Pokémon debilitado y pierdes a tu Mega."
        ],
        "verdict": "❌ FUGA TÁCTICA (Greed / Setup Trap): Intentar setearse cuando el rival tiene rango de OHKO directo es una de las mayores fugas competitivas (-1.85 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Raichu usó Nasty Plot para quedar a +2 SpA. Basculegion-M bajo lluvia desató Wave Crash potenciado: ¡OHKO masivo sobre Raichu-Mega-X! • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Quedas con un boost inútil en un Pokémon debilitado y pierdes a tu Mega."
      },
      {
        "id": "OPT-C",
        "label": "C) Raichu Protect pasivo esperando que el rival cambie de Pokémon",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Raichu usa Protect. Basculegion no cambia: golpea al Protect con Wave Crash.",
          "2. Basculegion conserva toda su salud intacta para el siguiente turno.",
          "3. En Turno 3 sigues expuesto a la lluvia sin haber eliminado la amenaza.",
          "5. [PROYECCIÓN TURNO +2]: Raichu usó Protect pasivo mientras Incineroar recibía Wave Crash brutal de Basculegion.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes la iniciativa y permites que el rival desgaste a tu soporte."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger sin un plan de contraataque cuando tienes el KO en la mano regala ventaja (-1.40 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Raichu usó Protect pasivo mientras Incineroar recibía Wave Crash brutal de Basculegion. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Cedes la iniciativa y permites que el rival desgaste a tu soporte."
      },
      {
        "id": "OPT-D",
        "label": "D) Raichu usa Focus Blast buscando una jugada de predicción de cambio",
        "optimal": false,
        "vpDelta": "-1.70 VP",
        "log": [
          "1. Focus Blast tiene 70% de precisión y no recibe STAB eléctrico.",
          "2. Basculegion no cambia: Focus Blast falla o inflige daño neutro insuficiente.",
          "3. Basculegion responde con Wave Crash y noquea a Raichu.",
          "5. [PROYECCIÓN TURNO +2]: Foco en Pelipper permitió a Basculegion atacar libremente y eliminar a Raichu.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Mal targeteado deja vivo al atacante más letal de la lluvia rival."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Wrong Threat Evaluation): Priorizar al setter sobre el atacante cuando este último amenaza OHKO pierde el juego (-1.65 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Foco en Pelipper permitió a Basculegion atacar libremente y eliminar a Raichu. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Mal targeteado deja vivo al atacante más letal de la lluvia rival."
      }
    ]
  },
  {
    "id": "SC-12",
    "title": "M317 Turno 3: Tilt & Greed vs Gengar-Mega Shadow Tag + Perish Song Trap",
    "driver": "Tilt",
    "code": "POS-01",
    "turnBadge": "TURNO 3 • PERISH SONG CONTADOR 1 • VP 3v3",
    "context": "Gengar-Mega rival cantó Perish Song y su Shadow Tag impide que tus Pokémon cambien. El contador de muerte está en 1. En lugar de entrar en pánico o hacer Protect pasivo, necesitas noquear a Gengar para desactivar Shadow Tag antes de que la trampa se cierre.",
    "oppSlots": [
      {
        "name": "Gengar-Mega",
        "item": "Gengarite",
        "ability": "Shadow Tag",
        "hp": 45,
        "status": "Trapper Activo"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 80,
        "status": "Parting Shot Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 90,
        "status": "Perish Count 1"
      },
      {
        "name": "Rotom-Wash",
        "item": "Sitrus Berry",
        "ability": "Levitate",
        "hp": 85,
        "status": "Perish Count 1"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Doble ataque ofensivo directo a Gengar-Mega (Stomping Tantrum + Thunderbolt)",
        "optimal": true,
        "vpDelta": "+1.90 VP",
        "log": [
          "1. Garchomp Stomping Tantrum conecta en Gengar-Mega y lo debilita por completo (0% HP)!",
          "2. Al caer Gengar-Mega, ¡la habilidad Shadow Tag se desactiva inmediatamente!",
          "3. Rotom-Wash Thunderbolt castiga a Incineroar.",
          "4. Con Shadow Tag roto, en el siguiente turno cambias libremente a tus dos Pokémon reseteando el contador de Perish Song a salvo!",
          "5. [PROYECCIÓN TURNO +2]: Gengar-Mega activó Perish Song y atrapa con Shadow Tag. Identificas el conteo (3T restantes) y concentras daño inmediato para noquear a Gengar antes del turno 3, o ejecutas U-turn / Volt Switch para forzar el escape.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Gengar debilitado desactiva Shadow Tag; tus piezas rotan y el rival sucumbe a su propio Perish Song (+1.75 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Mantener la calma ante Perish Trap, castigar al trampero con daño masivo y usar movimientos de pivotaje para escapar del Shadow Tag revierte la trampa a tu favor.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Gengar-Mega activó Perish Song y atrapa con Shadow Tag. Identificas el conteo (3T restantes) y concentras daño inmediato para noquear a Gengar antes del turno 3, o ejecutas U-turn / Volt Switch para forzar el escape. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Gengar debilitado desactiva Shadow Tag; tus piezas rotan y el rival sucumbe a su propio Perish Song (+1.75 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Entrar en pánico y usar doble Protect pasivo en Turno 3",
        "optimal": false,
        "vpDelta": "-2.20 VP",
        "log": [
          "1. Garchomp usa Protect. Rotom-Wash usa Protect.",
          "2. El rival no ataca: simplemente usa Fake Out o pasa el turno.",
          "3. Al final del Turno 3, el contador de Perish Song llega a 0!",
          "4. ¡Garchomp y Rotom-Wash caen debilitados simultáneamente! Desventaja irreversible.",
          "5. [PROYECCIÓN TURNO +2]: Tilt y desesperación: atacaste a ciegas sin plan de escape. El rival usó Protect y Disable.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Conteo de Perish llega a 0 y ambos aliados caen simultáneamente."
        ],
        "verdict": "❌ FUGA TÁCTICA (Tilt / Autopilot): Jugar con pánico ante Perish Song sin calcular turnos de salida regala la victoria al trampero (-1.80 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Tilt y desesperación: atacaste a ciegas sin plan de escape. El rival usó Protect y Disable. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Conteo de Perish llega a 0 y ambos aliados caen simultáneamente."
      },
      {
        "id": "OPT-C",
        "label": "C) Usar Swords Dance con Garchomp creyendo que tendrás más daño luego",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Garchomp usa Swords Dance (+2 Atk).",
          "2. Gengar usa Sludge Bomb sobre Rotom-Wash.",
          "3. El contador de Perish Song expira y Garchomp cae debilitado sin haber usado sus estadísticas aumentadas.",
          "5. [PROYECCIÓN TURNO +2]: Intentaste cambios directos que fallaron por la presencia de Shadow Tag.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Turno completamente perdido intentando una acción ilegal bajo sombra trampa."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Shadow Tag Ignorance): Intentar hard switch normal bajo Shadow Tag sin Ghost-type es un error básico de mecánicas (-1.85 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Intentaste cambios directos que fallaron por la presencia de Shadow Tag. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Turno completamente perdido intentando una acción ilegal bajo sombra trampa."
      },
      {
        "id": "OPT-D",
        "label": "D) Intentar cambiar repetidamente a la banca sin atacar a Gengar-Mega",
        "optimal": false,
        "vpDelta": "-1.75 VP",
        "log": [
          "1. Intentas cambiar de Pokémon... ¡La habilidad Shadow Tag bloquea el cambio!",
          "2. El juego rechaza la acción y pierdes el turno sin golpear al rival.",
          "3. Gengar usa Shadow Ball libremente y asegura el control del partido.",
          "5. [PROYECCIÓN TURNO +2]: Protect doble pasivo que solo beneficia al contador de Perish Song del rival.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: El rival agradece el turno libre y prepara su propio cambio final."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger contra Perish Trap sin amenaza ofensiva acelera tu propia eliminación (-1.50 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Protect doble pasivo que solo beneficia al contador de Perish Song del rival. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: El rival agradece el turno libre y prepara su propio cambio final."
      }
    ]
  },
  {
    "id": "SC-13",
    "title": "M323 Turno 2: POS-01 Dry Hard Switch Incineroar ante Pelipper + Basculegion en Lluvia",
    "driver": "Autopilot",
    "code": "POS-01",
    "turnBadge": "TURNO 2 • LLUVIA ACTIVA • VP 4v4",
    "context": "Tienes a Rillaboom y Farigiraf en campo. El rival tiene a Pelipper y Basculegion-M en Lluvia activa. Decides rotar por hábito a Incineroar para aplicar Intimidate, olvidando el daño de Wave Crash en lluvia.",
    "oppSlots": [
      {
        "name": "Basculegion-M",
        "item": "Life Orb",
        "ability": "Swift Swim",
        "hp": 100,
        "status": "Swift Swim (Spe 260)"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 90,
        "status": "Rain 4T"
      }
    ],
    "mySlots": [
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 100,
        "status": "Grassy Glide Ready"
      },
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 95,
        "status": "Trick Room Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Grassy Glide en Basculegion + Farigiraf Trick Room",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Grassy Glide (+1 prioridad en Grassy Terrain) conecta en Basculegion antes de que ataque (-74% HP)!",
          "2. Basculegion Wave Crash debilita a Rillaboom (-100% HP) pero recibe recoil masivo y queda a 8% HP.",
          "3. Pelipper ataca a Farigiraf sin noquearlo (-38% HP).",
          "4. Farigiraf castea Trick Room exitosamente: ahora controlas la velocidad para revertir el partido.",
          "5. [PROYECCIÓN TURNO +2]: Rillaboom usa Grassy Glide para presionar a Basculegion-M y Farigiraf usa Trick Room o Hyper Voice, manteniendo a Incineroar seguro en banca para entrar cuando la lluvia expire.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Neutralizas el ímpetu de lluvia y guardas a Incineroar con vida para el endgame (+1.65 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): No regalar a Incineroar en seco ante atacantes de agua bajo lluvia preserva tu mejor recurso defensivo para cuando el clima esté bajo control.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Rillaboom usa Grassy Glide para presionar a Basculegion-M y Farigiraf usa Trick Room o Hyper Voice, manteniendo a Incineroar seguro en banca para entrar cuando la lluvia expire. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Neutralizas el ímpetu de lluvia y guardas a Incineroar con vida para el endgame (+1.65 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Cambiar Farigiraf → Incineroar + Rillaboom Wood Hammer a Basculegion",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Retiras a Farigiraf → Entra Incineroar en seco.",
          "2. Basculegion bajo Swift Swim se mueve primero y usa Wave Crash en el slot de Incineroar: ¡OHKO masivo de 160% de daño en lluvia!",
          "3. Incineroar cae debilitado sin haber podido actuar ni aplicar Fake Out.",
          "4. Pierdes un recurso vital gratis por un cambio seco ante lluvia.",
          "5. [PROYECCIÓN TURNO +2]: Cambiaste a Incineroar en seco directamente a un Wave Crash bajo Lluvia: OHKO instantáneo (0% HP).",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Te quedas sin respuesta defensiva para el resto del combate."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar a Incineroar directamente ante un atacante de agua potenciado por lluvia es un error fatal de posicionamiento (-1.85 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Cambiaste a Incineroar en seco directamente a un Wave Crash bajo Lluvia: OHKO instantáneo (0% HP). • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Te quedas sin respuesta defensiva para el resto del combate."
      },
      {
        "id": "OPT-C",
        "label": "C) Rillaboom Protect + Farigiraf Psychic en Pelipper",
        "optimal": false,
        "vpDelta": "-1.35 VP",
        "log": [
          "1. Rillaboom usa Protect.",
          "2. Basculegion usa Wave Crash sobre Farigiraf: ¡OHKO masivo en lluvia (0% HP)!",
          "3. Farigiraf cae antes de poder meter Trick Room ni atacar.",
          "4. Rillaboom queda solo y aislado frente a la lluvia.",
          "5. [PROYECCIÓN TURNO +2]: Farigiraf usó Protect pasivo y Rillaboom atacó a Pelipper sin debilitarlo. Basculegion atacó con Wave Crash a Farigiraf.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Daño desbalanceado y pérdida de control del campo."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Inefficient Focus): No concentrar el daño en Basculegion permite al rival mantener su mayor potencia de fuego (-1.45 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Farigiraf usó Protect pasivo y Rillaboom atacó a Pelipper sin debilitarlo. Basculegion atacó con Wave Crash a Farigiraf. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Daño desbalanceado y pérdida de control del campo."
      },
      {
        "id": "OPT-D",
        "label": "D) Rillaboom U-turn a Pelipper + Farigiraf Hyper Voice",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Basculegion bajo Swift Swim ataca primero con Wave Crash y elimina a Rillaboom (0% HP) antes del U-turn.",
          "2. Pelipper usa Hurricane sobre Farigiraf (-45% HP).",
          "3. Farigiraf Hyper Voice no hace suficiente daño.",
          "4. Cedes la ventaja sin meter Trick Room.",
          "5. [PROYECCIÓN TURNO +2]: Rillaboom atacó con Wood Hammer y recibió daño masivo de retroceso además del ataque rival.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Desgaste autodestructivo deja la mesa servida para el sweep rival."
        ],
        "verdict": "❌ FUGA TÁCTICA (Autopilot / Greed): Autolesionarse con retroceso ante doble atacante rápido colapsa tu longevidad (-1.40 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Rillaboom atacó con Wood Hammer y recibió daño masivo de retroceso además del ataque rival. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Desgaste autodestructivo deja la mesa servida para el sweep rival."
      }
    ]
  },
  {
    "id": "SC-14",
    "title": "M324 Turno 1: POS-02 Lead Compression Frágil ante Sneasler + Dragonite",
    "driver": "Autopilot",
    "code": "POS-02",
    "turnBadge": "TURNO 1 • VP 4v4 • LEAD OFFENSIVE",
    "context": "Abriste con doble atacante frágil (Charizard-Mega-Y + Primarina) sin control de Fake Out ni redirección frente a Sneasler (Focus Sash) y Dragonite (Lum Berry).",
    "oppSlots": [
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 100,
        "status": "Fake Out Ready"
      },
      {
        "name": "Dragonite",
        "item": "Lum Berry",
        "ability": "Multiscale",
        "hp": 100,
        "status": "Extreme Speed (+2)"
      }
    ],
    "mySlots": [
      {
        "name": "Charizard-Mega-Y",
        "item": "Charizardite Y",
        "ability": "Drought",
        "hp": 100,
        "status": "Expuesto a Flinch"
      },
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 100,
        "status": "Expuesto a Físico"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard-Mega-Y Protect + Primarina Moonblast en Dragonite",
        "optimal": true,
        "vpDelta": "+1.40 VP",
        "log": [
          "1. Charizard usa Protect! Bloquea el Fake Out de Sneasler sin retroceder.",
          "2. Dragonite usa Extreme Speed en Primarina (-52% HP).",
          "3. Primarina resiste y responde con Moonblast super efectivo: rompe Multiscale y deja a Dragonite a 24% HP.",
          "4. Conservas el Sol y a tu Mega ileso para castigar con Heat Wave en Turno 2.",
          "5. [PROYECCIÓN TURNO +2]: Primarina usa Protect para absorber el Fake Out de Sneasler mientras Charizard-Mega-Y activa Drought y elimina a Sneasler con Heat Wave en Sol, rompiendo el Focus Sash y forzando a Dragonite a retroceder.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Clima controlado y ventaja posicional clara ante un Dragonite aislado (+1.65 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): La compresión de leads defensiva absorbe la agresión inicial sin conceder KOs tempranos, permitiendo al sol tomar el control del match.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Primarina usa Protect para absorber el Fake Out de Sneasler mientras Charizard-Mega-Y activa Drought y elimina a Sneasler con Heat Wave en Sol, rompiendo el Focus Sash y forzando a Dragonite a retroceder. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Clima controlado y ventaja posicional clara ante un Dragonite aislado (+1.65 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Doble ataque ofensivo (Heat Wave + Hyper Voice) sin proteger ningún slot",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Sneasler usa Fake Out sobre Charizard-Mega-Y: ¡retrocede y pierde el turno!",
          "2. Dragonite usa Extreme Speed (+2 prioridad) sobre Charizard: ¡conecta antes que Primarina y elimina a Charizard (0% HP)!",
          "3. Primarina lanza Hyper Voice pero el daño en sol está reducido y no logra KOs.",
          "4. Pierdes a tu Mega en Turno 1 con cero KOs logrados.",
          "5. [PROYECCIÓN TURNO +2]: Ambos aliados atacaron a Dragonite ignorando a Sneasler. Sneasler usó Close Combat sobre Primarina y Dragonite usó Extreme Speed.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Primarina cae debilitada en turno 1 y Charizard queda expuesto a Rock Slide."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-02 Lead Compression Failure): No respetar la presión de Fake Out y la velocidad de Sneasler resulta en colapso inmediato del lead (-1.75 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Ambos aliados atacaron a Dragonite ignorando a Sneasler. Sneasler usó Close Combat sobre Primarina y Dragonite usó Extreme Speed. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Primarina cae debilitada en turno 1 y Charizard queda expuesto a Rock Slide."
      },
      {
        "id": "OPT-C",
        "label": "C) Hard switch Charizard → Archaludon en seco",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Entra Archaludon en seco.",
          "2. Sneasler usa Close Combat con STAB super efectivo sobre Archaludon entrante (-65% HP)!",
          "3. Dragonite usa Stomping Tantrum en el mismo slot: Archaludon cae debilitado al entrar.",
          "4. Regalas tu mejor muro de acero por cambiar sin soporte.",
          "5. [PROYECCIÓN TURNO +2]: Charizard usó Protect y Primarina fue blanco de doble foco rival (-80% HP).",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Primarina queda inutilizada para el resto del combate."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Asymmetric Protection): Proteger el slot equivocado regala daño libre al compañero (-1.45 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Charizard usó Protect y Primarina fue blanco de doble foco rival (-80% HP). • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Primarina queda inutilizada para el resto del combate."
      },
      {
        "id": "OPT-D",
        "label": "D) Primarina Protect + Charizard Solar Beam en Dragonite",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Sneasler usa Fake Out en Charizard haciéndolo flinchear.",
          "2. Dragonite usa Extreme Speed en Charizard dejándolo a 15% HP.",
          "3. Solar Beam no es efectivo contra Dragón/Volador y Charizard queda casi muerto sin atacar.",
          "4. Mala asignación de objetivo y falta de protección.",
          "5. [PROYECCIÓN TURNO +2]: Cambio seco de Charizard a banca entregó un turno libre a Sneasler para meter Swords Dance.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Sneasler a +2 Atk con Unburden listo barre a tu equipo."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Ceder la iniciativa a un sweeper con Swords Dance en turno 1 sentencia la partida (-1.70 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Cambio seco de Charizard a banca entregó un turno libre a Sneasler para meter Swords Dance. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Sneasler a +2 Atk con Unburden listo barre a tu equipo."
      }
    ]
  },
  {
    "id": "SC-15",
    "title": "M325 Turno 3: POS-03 Passive Protect ante Archaludon Stamina + Leftovers",
    "driver": "Autopilot",
    "code": "POS-03",
    "turnBadge": "TURNO 3 • VP 3v3 • CONTROL DE TEMPO",
    "context": "Archaludon rival tiene +1 Def tras Stamina y recupera vida con Leftovers. Tu Rillaboom y Garchomp están en campo. Tienes la tentación de dar doble Protect por inercia para 'pensar la jugada'.",
    "oppSlots": [
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 75,
        "status": "+1 Def / Leftovers"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 50,
        "status": "Lluvia Activa"
      }
    ],
    "mySlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 85,
        "status": "Ground STAB Ready"
      },
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 90,
        "status": "Wood Hammer Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Garchomp Stomping Tantrum en Archaludon + Rillaboom Wood Hammer en Pelipper",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Rillaboom Wood Hammer conecta en Pelipper y lo noquea de inmediato (0% HP), cortando el soporte de lluvia!",
          "2. Garchomp desata Stomping Tantrum con STAB Terrestre super efectivo sobre Archaludon: ¡82% de daño a pesar de Stamina!",
          "3. Archaludon cae debilitado antes de poder disparar Electro Shot.",
          "4. Doble KO fulminante que asegura el partido en un solo turno.",
          "5. [PROYECCIÓN TURNO +2]: Garchomp usa Stomping Tantrum directo a Archaludon (daño físico de Tierra super efectivo sin multihits para no regalar cargas de Stamina) y Rillaboom conecta Wood Hammer en Pelipper.",
          "6. [PROYECCIÓN TURNO +3 / WINCON]: Archaludon cae antes de setearse y el clima de lluvia se apaga con la caída de Pelipper (+1.75 VP)."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Castigar a Archaludon con daño concentrado de un solo golpe evita disparar múltiples cargas de Stamina y elimina la amenaza antes de que Leftovers recupere su salud.",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Garchomp usa Stomping Tantrum directo a Archaludon (daño físico de Tierra super efectivo sin multihits para no regalar cargas de Stamina) y Rillaboom conecta Wood Hammer en Pelipper. • 6. [PROYECCIÓN TURNO +3 / WINCON]: Archaludon cae antes de setearse y el clima de lluvia se apaga con la caída de Pelipper (+1.75 VP)."
      },
      {
        "id": "OPT-B",
        "label": "B) Doble Protect pasivo (Garchomp Protect + Rillaboom Protect)",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Garchomp usa Protect. Rillaboom usa Protect.",
          "2. Archaludon aprovecha el turno libre para usar Iron Defense (+2 Def adicional) y se cura con Leftovers (+6% HP).",
          "3. Pelipper usa Tailwind gratis bajo la lluvia duplicando su velocidad.",
          "4. En Turno 4, Archaludon tiene +3 Def y el rival ataca primero con Body Press potenciado.",
          "5. [PROYECCIÓN TURNO +2]: Usaste ataques multihit débiles o divididos. Archaludon acumuló +3 en Defensa física por Stamina y curó con Leftovers.",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Archaludon con +3 Def desata Body Press de 200+ daño y barre a Garchomp de un solo golpe."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Stamina Feed): Disparar la habilidad Stamina del rival sin asegurar el KO convierte a Archaludon en una muralla indestructible (-1.80 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Usaste ataques multihit débiles o divididos. Archaludon acumuló +3 en Defensa física por Stamina y curó con Leftovers. • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Archaludon con +3 Def desata Body Press de 200+ daño y barre a Garchomp de un solo golpe."
      },
      {
        "id": "OPT-C",
        "label": "C) Rillaboom Grassy Glide en Archaludon + Garchomp Swords Dance",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Grassy Glide conecta pero es resistido por Acero/Dragón: ¡activa Stamina (+2 Def) sin hacer daño!",
          "2. Archaludon usa Body Press en Garchomp (-55% HP).",
          "3. Pelipper usa Hurricane en Rillaboom (-60% HP).",
          "4. Tu intento de setup le regaló más defensa física al rival.",
          "5. [PROYECCIÓN TURNO +2]: Garchomp y Rillaboom usaron Protect pasivo. Archaludon usó Electro Shot libremente en lluvia (+1 SpA).",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Archaludon gana +1 en SpA y recupera HP con Leftovers gratis."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Permitir a Archaludon ganar turnos gratis bajo lluvia acelera su bola de nieve ofensiva (-1.50 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Garchomp y Rillaboom usaron Protect pasivo. Archaludon usó Electro Shot libremente en lluvia (+1 SpA). • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Archaludon gana +1 en SpA y recupera HP con Leftovers gratis."
      },
      {
        "id": "OPT-D",
        "label": "D) Garchomp Dragon Claw en Pelipper + Rillaboom Knock Off en Archaludon",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Dragon Claw no logra OHKO en Pelipper.",
          "2. Archaludon usa Electro Shot en Garchomp (no afecta por tipo Tierra) pero Pelipper responde con Weather Ball Agua en Garchomp (-70% HP).",
          "3. Dejas vivo a ambos oponentes con daño fragmentado.",
          "5. [PROYECCIÓN TURNO +2]: Foco exclusivo en Pelipper ignorando a Archaludon permitió a este último ejecutar Draco Meteor sobre Garchomp (OHKO).",
          "6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu atacante de tierra y quedas sin forma de romper a Archaludon."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Wrong Threat Focus): Ignorar la amenaza que tiene rango de OHKO directo sobre tu atacante clave pierde el juego (-1.65 VP).",
        "futureProjection": "5. [PROYECCIÓN TURNO +2]: Foco exclusivo en Pelipper ignorando a Archaludon permitió a este último ejecutar Draco Meteor sobre Garchomp (OHKO). • 6. [PROYECCIÓN TURNO +3 / DERROTA]: Pierdes a tu atacante de tierra y quedas sin forma de romper a Archaludon."
      }
    ]
  },
  {
    "id": "SC-16",
    "title": "M326 Turno 1: SPD-02 Conflicto de Climas (Torkoal vs Pelipper / Basculegion)",
    "driver": "Autopilot",
    "code": "SPD-02",
    "turnBadge": "TURNO 1 • DISPUTA DE CLIMA • VP 4v4",
    "context": "Abriste con Torkoal (Drought) y Charizard-Mega-Y frente a Pelipper (Drizzle) y Basculegion-M. Como Torkoal es más lento (Spe base 20 vs 65), tu Drought se activó al final y ganaste el Sol. Si atacas en automático con moves de Agua o cambias a Torkoal, pierdes el clima.",
    "oppSlots": [
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 100,
        "status": "Clima Perdido (Sol)"
      },
      {
        "name": "Basculegion-M",
        "item": "Life Orb",
        "ability": "Swift Swim",
        "hp": 100,
        "status": "Swift Swim Inactivo"
      }
    ],
    "mySlots": [
      {
        "name": "Charizard-Mega-Y",
        "item": "Charizardite Y",
        "ability": "Drought",
        "hp": 100,
        "status": "Sol Activo (+50% Fire)"
      },
      {
        "name": "Torkoal",
        "item": "Heat Rock",
        "ability": "Drought",
        "hp": 100,
        "status": "Spe Base 20"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard Solar Beam en Basculegion + Torkoal Eruption en área",
        "optimal": true,
        "vpDelta": "+1.90 VP",
        "log": [
          "1. Bajo Sol, Solar Beam se dispara al instante sin turno de carga!",
          "2. Charizard fulmina a Basculegion con Solar Beam super efectivo: ¡OHKO directo (0% HP) antes de que ataque!",
          "3. Torkoal a 100% HP desata Eruption potenciada por Sol: impacta masivamente a Pelipper (-68% HP).",
          "4. Pelipper queda solo y sin su sweeper de agua."
        ],
        "verdict": "✅ ÓPTIMO (+1.90 VP): Capitalizas el Sol activo con Solar Beam instantáneo y Eruption de área para quebrar el núcleo de lluvia en Turno 1."
      },
      {
        "id": "OPT-B",
        "label": "B) Cambiar Torkoal → Rotom-Wash + Charizard Heat Wave",
        "optimal": false,
        "vpDelta": "-1.55 VP",
        "log": [
          "1. Retiras a Torkoal → Entra Rotom-Wash en seco.",
          "2. Pelipper usa Tailwind! Duplica la velocidad de su equipo.",
          "3. Basculegion, superando a Charizard incluso sin lluvia, usa Wave Crash sobre Charizard: ¡OHKO a tu Mega!",
          "4. Cedes la iniciativa de velocidad sin haber eliminado la amenaza principal."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 & Autopilot): Cambiar en seco a un setter de clima en lugar de atacar regala tempo y tu Mega (-1.55 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Charizard Protect + Torkoal Protect (Doble Protect de tanteo)",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Ambos usan Protect.",
          "2. Pelipper cambia por otro Pokémon o castea Tailwind tranquilamente.",
          "3. Desperdicias un turno completo de Sol a máxima potencia.",
          "4. El rival gana posicionamiento gratis."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Quemar turnos de Sol con doble Protect anula tu propia ventaja de clima (-1.40 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Charizard Heat Wave en Pelipper + Torkoal Stealth Rock",
        "optimal": false,
        "vpDelta": "-1.65 VP",
        "log": [
          "1. Pelipper resiste Heat Wave gracias a su tipo Agua.",
          "2. Basculegion ataca con Wave Crash a Charizard eliminándolo por completo.",
          "3. Torkoal pone Stealth Rock, un movimiento de nulo impacto inmediato en dobles 4v4.",
          "4. Desperdicias el turno ofensivo en hazard pasivo."
        ],
        "verdict": "❌ ERROR ESTRATÉGICO (Greed de Hazards): Poner trampa de rocas en un turno crítico de 4v4 dobles pierde la partida (-1.65 VP)."
      }
    ]
  },
  {
    "id": "SC-17",
    "title": "M327 Turno 3: TGT-01 Protect Tunneling en Farigiraf mientras Armarouge Carga",
    "driver": "Autopilot",
    "code": "TGT-01",
    "turnBadge": "TURNO 3 • VP 3v3 • SEÑALIZACIÓN DEFENSIVA",
    "context": "Farigiraf está a 20% HP y tiene Armor Tail activa. Su compañero Armarouge está a 100% HP y prepara Expanding Force. Farigiraf tiene Protect en su set y es muy evidente que protegerá para salvar su vida.",
    "oppSlots": [
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 20,
        "status": "Protect Predecible"
      },
      {
        "name": "Armarouge",
        "item": "Life Orb",
        "ability": "Flash Fire",
        "hp": 100,
        "status": "Expanding Force"
      }
    ],
    "mySlots": [
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 90,
        "status": "Knock Off Ready"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 85,
        "status": "Kowtow Cleave Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Knock Off en Armarouge + Kingambit Kowtow Cleave en Armarouge",
        "optimal": true,
        "vpDelta": "+1.85 VP",
        "log": [
          "1. Farigiraf usa Protect! Esperaba el ataque desesperado sobre sus 20% HP.",
          "2. Incineroar Knock Off conecta de lleno en Armarouge (-55% HP) y despoja su Life Orb!",
          "3. Kingambit desata Kowtow Cleave super efectivo con STAB Siniestro: ¡OHKO rotundo sobre Armarouge (0% HP)!",
          "4. Farigiraf queda completamente sola y sin atacante especial."
        ],
        "verdict": "✅ ÓPTIMO (+1.85 VP): Castigas el slot ofensivo abierto con doble ataque Siniestro ignorando el Protect evidente de Farigiraf."
      },
      {
        "id": "OPT-B",
        "label": "B) Doble ataque enfocado en Farigiraf para asegurar la baja",
        "optimal": false,
        "vpDelta": "-1.75 VP",
        "log": [
          "1. Farigiraf usa Protect!",
          "2. Incineroar y Kingambit se estrellan contra el Protect de Farigiraf (0 daño total).",
          "3. Armarouge desata Armor Cannon potenciado por Life Orb sobre Kingambit: ¡OHKO crítico con debilidad de Fuego!",
          "4. Pierdes a tu mejor atacante y el rival mantiene a sus dos piezas vivas."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Protect Tunneling): Obsesionarse con rematar a un soporte con Protect cantado te cuesta tu pieza clave (-1.75 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Kingambit Sucker Punch en Armarouge + Incineroar Flare Blitz en Farigiraf",
        "optimal": false,
        "vpDelta": "-1.90 VP",
        "log": [
          "1. Kingambit intenta Sucker Punch... ¡Armor Tail de Farigiraf anula todo movimiento prioritario rival!",
          "2. El ataque prioritario falla automáticamente.",
          "3. Flare Blitz choca contra el Protect de Farigiraf.",
          "4. Armarouge noquea a Kingambit con Armor Cannon libremente."
        ],
        "verdict": "❌ ERROR MECÁNICO (MEC-01 Armor Tail Collision): Usar prioridad frente a la habilidad Armor Tail resulta en fallo absoluto (-1.90 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Incineroar Parting Shot en Armarouge + Kingambit Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Incineroar usa Parting Shot reduciendo stats y cambia a la banca.",
          "2. Kingambit usa Protect pasivo.",
          "3. Armarouge ataca al Protect y Farigiraf se salva sin recibir daño.",
          "4. Cedes la iniciativa sin haber logrado KOs."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 & Autopilot): Jugar a reducir stats en lugar de tomar un KO limpio sobre el atacante rival (-1.30 VP)."
      }
    ]
  },
  {
    "id": "SC-18",
    "title": "M328 Turno 1: MEC-01 Fake Out hacia Farigiraf con Armor Tail",
    "driver": "Autopilot",
    "code": "MEC-01",
    "turnBadge": "TURNO 1 • VP 4v4 • HABILIAD DE BLOQUEO",
    "context": "Abres con Incineroar y Rillaboom frente a Farigiraf y Torkoal / Armarouge. La costumbre de clickear Fake Out en Turno 1 te impulsa a lanzarlo al slot 1 donde está Farigiraf.",
    "oppSlots": [
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 100,
        "status": "Armor Tail Activo"
      },
      {
        "name": "Armarouge",
        "item": "Life Orb",
        "ability": "Flash Fire",
        "hp": 100,
        "status": "Expanding Force"
      }
    ],
    "mySlots": [
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Fake Out Ready"
      },
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 100,
        "status": "Knock Off Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Knock Off en Armarouge + Rillaboom U-turn en Farigiraf",
        "optimal": true,
        "vpDelta": "+1.65 VP",
        "log": [
          "1. Como Armor Tail sólo bloquea ataques prioritarios, Knock Off y U-turn se ejecutan con normalidad!",
          "2. Incineroar Knock Off golpea a Armarouge (-54% HP) y quita su Life Orb.",
          "3. Rillaboom U-turn conecta super efectivo en Farigiraf (-42% HP) y rota hacia un compañero seguro.",
          "4. Neutralizas la ofensiva rival sin desperdiciar turnos de ataque."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): Reconoces la inmunidad a prioridad de Armor Tail y ejecutas ataques convencionales con control de daño y pivoteo."
      },
      {
        "id": "OPT-B",
        "label": "B) Incineroar Fake Out en Farigiraf + Rillaboom Wood Hammer en Farigiraf",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Incineroar intenta Fake Out... ¡La habilidad Armor Tail de Farigiraf impide el uso de movimientos prioritarios!",
          "2. ¡Fake Out falla completamente sin hacer daño ni causar flinch!",
          "3. Armarouge aprovecha y desata Armor Cannon sobre Rillaboom: ¡OHKO demoledor!",
          "4. Farigiraf resiste Wood Hammer y castea Trick Room a placer."
        ],
        "verdict": "❌ ERROR MECÁNICO (MEC-01 Armor Tail Collision): Clickear Fake Out ante Armor Tail desperdicia la acción y concede KO al oponente (-1.80 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Rillaboom Grassy Glide en Armarouge + Incineroar Flare Blitz en Farigiraf",
        "optimal": false,
        "vpDelta": "-1.70 VP",
        "log": [
          "1. Rillaboom intenta Grassy Glide con prioridad: ¡Armor Tail lo bloquea de inmediato!",
          "2. Armarouge ataca primero con Armor Cannon.",
          "3. Incineroar hace daño a Farigiraf pero recibe recoil.",
          "4. Quedas sin tempo y con Rillaboom debilitado."
        ],
        "verdict": "❌ ERROR MECÁNICO (MEC-01): Cualquier ataque prioritario (incluyendo Grassy Glide) es bloqueado por Armor Tail (-1.70 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Doble Protect pasivo en Turno 1",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Ambos usan Protect.",
          "2. Farigiraf mete Trick Room gratis.",
          "3. Armarouge usa Nasty Plot o Calm Mind sin ser perturbado.",
          "4. En Turno 2 estás bajo Trick Room con el rival potenciado."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Regalar el primer turno ante Trick Room te condena a jugar a remolque (-1.45 VP)."
      }
    ]
  },
  {
    "id": "SC-19",
    "title": "M329 Turno 1: POS-02 Falta de Redirección vs Unburden Sneasler Close Combat",
    "driver": "Autopilot",
    "code": "POS-02",
    "turnBadge": "TURNO 1 • VP 4v4 • LEAD EXPLOSIVO",
    "context": "Abres con Archaludon y Kingambit frente a Sneasler (Focus Sash) e Incineroar. Tu lead carece de redirección (Follow Me) o Protect en ambos slots, exponiendo a tus dos Pokémon de tipo Acero a Close Combat STAB.",
    "oppSlots": [
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 100,
        "status": "Close Combat STAB"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Fake Out Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 100,
        "status": "Doble Débil Lucha"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 100,
        "status": "4x Débil Lucha"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Kingambit Protect + Archaludon Body Press en Sneasler",
        "optimal": true,
        "vpDelta": "+1.60 VP",
        "log": [
          "1. Kingambit usa Protect! Resguarda su debilidad cuádruple a Lucha.",
          "2. Sneasler intenta Close Combat en Kingambit: ¡bloqueado por Protect!",
          "3. Incineroar usa Fake Out en Archaludon (-8% HP) y activa Stamina (+1 Def).",
          "4. Salvas a tu Kingambit de un OHKO directo y preparas represalia en Turno 2."
        ],
        "verdict": "✅ ÓPTIMO (+1.60 VP): Proteger al slot con debilidad 4x neutraliza el nuke de combate de Sneasler y desgasta el Fake Out rival."
      },
      {
        "id": "OPT-B",
        "label": "B) Doble ataque directo (Iron Head + Flash Cannon) sin proteger a Kingambit",
        "optimal": false,
        "vpDelta": "-2.10 VP",
        "log": [
          "1. Incineroar usa Fake Out en Archaludon (flincheado).",
          "2. Sneasler desata Close Combat sobre Kingambit: ¡OHKO brutal de 400% de efectividad (0% HP)!",
          "3. Kingambit cae sin atacar.",
          "4. Pierdes tu condición de victoria en Turno 1."
        ],
        "verdict": "❌ ERROR FATAL (POS-02 Lead Compression Failure): No proteger una debilidad cuádruple frente al tipo Lucha más rápido del formato es derrota inmediata (-2.10 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Hard switch Kingambit → Pelipper en seco",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Entra Pelipper en seco.",
          "2. Incineroar usa Knock Off despojando el Damp Rock de Pelipper (-40% HP).",
          "3. Sneasler redirige o golpea a Archaludon con Close Combat (-65% HP).",
          "4. Tus slots quedan severamente dañados al entrar."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar en seco absorbiendo golpes debilita la estructura de tu equipo (-1.50 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Kingambit Sucker Punch en Sneasler + Archaludon Protect",
        "optimal": false,
        "vpDelta": "-1.70 VP",
        "log": [
          "1. Incineroar usa Fake Out (+3 prioridad) en Kingambit antes de que ejecute Sucker Punch (+1 prioridad)!",
          "2. Kingambit retrocede y no puede atacar.",
          "3. Sneasler desata Close Combat y aniquila a Kingambit.",
          "4. Falla de comprensión de prioridades relativas."
        ],
        "verdict": "❌ ERROR DE VELOCIDAD (SPD-01 & Autopilot): Fake Out tiene +3 de prioridad y siempre supera al Sucker Punch (+1) de Kingambit (-1.70 VP)."
      }
    ]
  },
  {
    "id": "SC-20",
    "title": "M330 Turno 3: TGT-01 Protect Tunneling vs Kingambit (15% HP)",
    "driver": "Tunnel_Vision",
    "code": "TGT-01",
    "turnBadge": "TURNO 3 • VP 3v3 • PRESIÓN DE PROTECT",
    "context": "Kingambit rival está a 15% HP pero tiene Protect cantado. A su lado Primarina (80% HP) prepara Hyper Voice. Tienes a Archaludon y a Incineroar en campo.",
    "oppSlots": [
      {
        "name": "Kingambit",
        "item": "Leftovers",
        "ability": "Defiant",
        "hp": 15,
        "status": "Protect Telegrafiado"
      },
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 80,
        "status": "Hyper Voice Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Archaludon",
        "item": "Rocky Helmet",
        "ability": "Stamina",
        "hp": 85,
        "status": "Spe 105"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 70,
        "status": "Spe 80"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Archaludon Electro Shot en Primarina + Incineroar Knock Off en Primarina",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Kingambit usa Protect! Absorbe cualquier intento de foco.",
          "2. Incineroar conecta Knock Off en Primarina removiendo su Mystic Water (-40% HP).",
          "3. Archaludon carga y desata Electro Shot en Primarina debilitándola por completo.",
          "4. Kingambit queda solo e indefenso para el turno siguiente."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Ignoras el Protect cantado de Kingambit y castigas al partner ofensivo para asegurar la ventaja de piezas."
      },
      {
        "id": "OPT-B",
        "label": "B) Archaludon Body Press en Kingambit + Incineroar Flare Blitz en Kingambit",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Kingambit usa Protect! Bloquea exitosamente ambos ataques.",
          "2. Archaludon Body Press choca contra Protect (Sin efecto).",
          "3. Incineroar Flare Blitz choca contra Protect (Sin efecto).",
          "4. Primarina desata Hyper Voice potenciado (-55% HP a ambos aliados)."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Protect Tunneling): Foco ciego al slot moribundo permitiendo al compañero rival actuar gratis (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Archaludon Protect + Incineroar Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Ambos aliados usan Protect.",
          "2. Kingambit recupera salud pasiva con Leftovers.",
          "3. Primarina queda lista para atacar el siguiente turno sin presión.",
          "4. Cedes la iniciativa sin generar daño."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger sin razón cuando tenías ventaja de tempo regala iniciativa (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Incineroar por Rillaboom + Archaludon Flash Cannon a Kingambit",
        "optimal": false,
        "vpDelta": "-1.55 VP",
        "log": [
          "1. Rotas a Rillaboom en seco recibiendo el Hyper Voice de Primarina (-42% HP).",
          "2. Kingambit protege contra Flash Cannon.",
          "3. Expones a un atacante clave sin necesidad."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 / Tilt): Rotación seca innecesaria frente a un ataque de área cantado (-1.55 VP)."
      }
    ]
  },
  {
    "id": "SC-21",
    "title": "M331 Turno 2: TGT-02 Close Combat a Archaludon redirigido por Maushold Follow Me",
    "driver": "Tunnel_Vision",
    "code": "TGT-02",
    "turnBadge": "TURNO 2 • REDIRECCIÓN ACTIVA • VP 4v4",
    "context": "El rival tiene a Maushold (Friend Guard / Follow Me) protegiendo a Archaludon. Tienes a Lucario-Mega y Garchomp en campo.",
    "oppSlots": [
      {
        "name": "Maushold",
        "item": "Focus Sash",
        "ability": "Friend Guard",
        "hp": 100,
        "status": "Follow Me Ready"
      },
      {
        "name": "Archaludon",
        "item": "Rocky Helmet",
        "ability": "Stamina",
        "hp": 100,
        "status": "Spe 105"
      }
    ],
    "mySlots": [
      {
        "name": "Lucario-Mega",
        "item": "Lucarionite",
        "ability": "Adaptability",
        "hp": 100,
        "status": "Spe 180"
      },
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Spe 169"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Lucario-Mega Aura Sphere en Maushold + Garchomp Earthquake",
        "optimal": true,
        "vpDelta": "+1.65 VP",
        "log": [
          "1. Maushold usa Follow Me (+2 prioridad) para redirigir ataques singulares.",
          "2. Lucario-Mega Aura Sphere impacta en Maushold y rompe su Focus Sash (1% HP).",
          "3. Garchomp ejecuta Earthquake (Ataque de Área no redirigible): elimina a Maushold y daña a Archaludon (-48% HP).",
          "4. Neutralizas la redirección y comprometes al sweeper rival."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): Usar ataques de área y foco disciplinado al señuelo anula la estrategia de Follow Me."
      },
      {
        "id": "OPT-B",
        "label": "B) Lucario-Mega Close Combat en Archaludon + Garchomp Stomping Tantrum en Archaludon",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Maushold activa Follow Me: absorbe ambos ataques singulares.",
          "2. Close Combat golpea a Maushold rompiendo su Focus Sash.",
          "3. Stomping Tantrum es absorbido por Maushold que sobrevive a 1 HP.",
          "4. Archaludon queda totalmente ileso y castiga con Body Press a Lucario (OHKO)."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-02 Redirection Error): Lanzar dos ataques singulares hacia el protegido en vez de usar área contra Follow Me (-1.80 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Lucario-Mega Protect + Garchomp Swords Dance",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Lucario usa Protect.",
          "2. Garchomp intenta Swords Dance.",
          "3. Archaludon usa Draco Meteor sobre Garchomp (-88% HP).",
          "4. Pierdes tempo decisivo ante la presión rival."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Setup innecesario cuando podías eliminar la pantalla de redirección (-1.40 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Lucario por Incineroar + Garchomp Protect",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Cambias a Lucario recibiendo daño en seco.",
          "2. El rival mantiene el control del tablero con Maushold intacto.",
          "3. Desventaja posicional."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Ceder la iniciativa cuando tenías ventaja de velocidad pura (-1.50 VP)."
      }
    ]
  },
  {
    "id": "SC-22",
    "title": "M332 Turno 4: TGT-03 Double KO Waste en Pelipper (8% HP)",
    "driver": "Tunnel_Vision",
    "code": "TGT-03",
    "turnBadge": "TURNO 4 • VP 2v2 • RECURSOS CRÍTICOS",
    "context": "Pelipper rival está a 8% HP y cae ante cualquier golpe mínimo. A su lado Basculegion-M (100% HP) en lluvia amenaza con barrer. Tienes a Rillaboom y Primarina.",
    "oppSlots": [
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 8,
        "status": "8% HP restante"
      },
      {
        "name": "Basculegion-M",
        "item": "Life Orb",
        "ability": "Swift Swim",
        "hp": 100,
        "status": "Swift Swim (Spe 260)"
      }
    ],
    "mySlots": [
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 90,
        "status": "Grassy Glide Ready"
      },
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 75,
        "status": "Spe 80"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Grassy Glide en Basculegion + Primarina Moonblast en Basculegion",
        "optimal": true,
        "vpDelta": "+1.80 VP",
        "log": [
          "1. Grassy Glide con prioridad (+1) conecta en Basculegion antes de que ataque (-72% HP)!",
          "2. Pelipper intenta Hurricane sobre Rillaboom (-42% HP).",
          "3. Primarina Moonblast remata a Basculegion (0% HP).",
          "4. Pelipper queda solo y en rango de KO para el siguiente turno: victoria asegurada."
        ],
        "verdict": "✅ ÓPTIMO (+1.80 VP): Concentras el daño en el atacante peligroso en lugar de desperdiciar ataques en un slot ya irrelevante."
      },
      {
        "id": "OPT-B",
        "label": "B) Rillaboom Wood Hammer en Pelipper + Primarina Hyper Voice en Pelipper",
        "optimal": false,
        "vpDelta": "-1.90 VP",
        "log": [
          "1. Rillaboom Wood Hammer sobre-aniquila a Pelipper (0% HP).",
          "2. Basculegion bajo lluvia desata Wave Crash sobre Primarina (OHKO).",
          "3. Hyper Voice de Primarina no se ejecuta al estar debilitada.",
          "4. Rillaboom queda solo frente a Basculegion a toda velocidad."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Damage Overkill): Gastar dos ataques en un objetivo que caía con uno solo le permite al atacante rival barrer (-1.90 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Rillaboom Protect + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. Basculegion y Pelipper reposicionan su ventaja.",
          "3. Pierdes un turno de Grassy Terrain gratis."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Turno pasivo sin valor ofensivo cuando tenías prioridad disponible (-1.45 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Rillaboom U-turn en Basculegion + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Basculegion ataca primero por lluvia y elimina a Rillaboom antes del U-turn.",
          "2. Pelipper presiona a Primarina protegida.",
          "3. Cedes un recurso sin cobrar nada a cambio."
        ],
        "verdict": "❌ FUGA TÁCTICA (SPD-01 / Autopilot): Olvidar la velocidad de Swift Swim bajo lluvia activa (-1.60 VP)."
      }
    ]
  },
  {
    "id": "SC-23",
    "title": "M333 Turno 2: POS-01 Dry Switch hacia Draco Meteor de Archaludon",
    "driver": "Tunnel_Vision",
    "code": "POS-01",
    "turnBadge": "TURNO 2 • VP 3v3 • CONTROL DE ROTACIÓN",
    "context": "Tienes a Kingambit y Farigiraf en campo. El rival tiene a Archaludon y Pelipper en lluvia. Deseas meter a Dragonite para aprovechar Multiscale, pero Archaludon amenaza Draco Meteor.",
    "oppSlots": [
      {
        "name": "Archaludon",
        "item": "Rocky Helmet",
        "ability": "Stamina",
        "hp": 90,
        "status": "Draco Meteor Ready"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 85,
        "status": "Rain 3T"
      }
    ],
    "mySlots": [
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 100,
        "status": "Spe 70"
      },
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 90,
        "status": "Trick Room Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Kingambit Kowtow Cleave en Archaludon + Farigiraf Trick Room",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Archaludon usa Electro Shot sobre Farigiraf (-45% HP).",
          "2. Kingambit conecta Kowtow Cleave en Archaludon (-42% HP).",
          "3. Farigiraf resiste y activa Trick Room exitosamente.",
          "4. Con Trick Room activo, Kingambit ahora se moverá primero el próximo turno."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Mantener la estructura del campo y activar Trick Room asegura control total de velocidad."
      },
      {
        "id": "OPT-B",
        "label": "B) Cambiar Farigiraf por Dragonite + Kingambit Iron Head en Pelipper",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Rotas a Farigiraf → Entra Dragonite en seco.",
          "2. Archaludon predice o ataca ese slot con Draco Meteor STAB: rompe Multiscale y hace OHKO a Dragonite.",
          "3. Dragonite cae sin haber ejecutado una sola acción.",
          "4. Pierdes a tu wincon primaria por un cambio seco injustificado."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar a un Dragón en seco frente a Archaludon cuesta una pieza vital (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Kingambit Protect + Farigiraf Protect",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. El rival no gasta recursos ni recibe daño.",
          "3. Desperdicias un turno de lluvia rival."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Doble Protect pasivo cuando debías establecer Trick Room (-1.25 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Kingambit Sucker Punch en Archaludon + Farigiraf Hyper Voice",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Sucker Punch hace poco daño a Archaludon por su alto bulk físico y activa Stamina (+1 Def).",
          "2. Archaludon ataca con Body Press a Kingambit (-65% HP).",
          "3. Farigiraf no mete Trick Room y quedas en desventaja de velocidad."
        ],
        "verdict": "❌ FUGA TÁCTICA (SPD-01 Autopilot): Atacar sin control de velocidad permite al rival mantener la iniciativa (-1.40 VP)."
      }
    ]
  },
  {
    "id": "SC-24",
    "title": "M334 Turno 3: MEC-01 Prioridad Grassy Glide a Sneasler en Terreno Psíquico",
    "driver": "Tunnel_Vision",
    "code": "MEC-01",
    "turnBadge": "TURNO 3 • PSYCHIC TERRAIN ACTIVO • VP 3v3",
    "context": "El rival tiene activo el Terreno Psíquico (invocado por Indeedee). Sneasler rival está a 30% HP y apoyado por Indeedee-F. Tienes a Rillaboom y Kingambit en campo.",
    "oppSlots": [
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 30,
        "status": "Grounded en Psychic Terrain"
      },
      {
        "name": "Indeedee-F",
        "item": "Psychic Seed",
        "ability": "Psychic Surge",
        "hp": 75,
        "status": "Psychic Terrain 3T"
      }
    ],
    "mySlots": [
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 80,
        "status": "En Reserva/Campo"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 90,
        "status": "Sucker Punch Listo"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Wood Hammer en Indeedee-F + Kingambit Kowtow Cleave en Sneasler",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Rillaboom usa Wood Hammer (ataque sin prioridad) sobre Indeedee-F: OHKO masivo (-100% HP)!",
          "2. Sneasler intenta Dire Claw sobre Rillaboom (-45% HP).",
          "3. Kingambit conecta Kowtow Cleave (sin prioridad) sobre Sneasler y lo debilita.",
          "4. Consigues doble KO ignorando las restricciones de prioridad del terreno."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Evitas movimientos de prioridad bloqueados por Terreno Psíquico y ejecutas ataques directos para arrasar el campo."
      },
      {
        "id": "OPT-B",
        "label": "B) Rillaboom Grassy Glide en Sneasler + Kingambit Sucker Punch en Sneasler",
        "optimal": false,
        "vpDelta": "-1.95 VP",
        "log": [
          "1. Rillaboom intenta Grassy Glide (+1 prioridad) sobre Sneasler: ¡El Terreno Psíquico bloquea la prioridad sobre el objetivo en suelo!",
          "2. Kingambit intenta Sucker Punch (+1 prioridad) sobre Sneasler: ¡El Terreno Psíquico bloquea la prioridad!",
          "3. Ambos movimientos fallan completamente sin hacer 1 punto de daño.",
          "4. Sneasler desata Close Combat y debilita a Kingambit (OHKO)."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Terrain Priority Collision): Terreno Psíquico bloquea ataques con prioridad contra Pokémon grounded (-1.95 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Kingambit Protect + Rillaboom Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Ambos aliados usan Protect.",
          "2. Indeedee apoya a Sneasler con Helping Hand.",
          "3. Pierdes un turno sin modificar el terreno ni causar bajas."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger sin planificar el cambio de terreno regala tempo (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Rillaboom U-turn en Indeedee-F + Kingambit Sucker Punch en Indeedee-F",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Sucker Punch vuelve a fallar por la protección del Terreno Psíquico.",
          "2. U-turn conecta en Indeedee pero no basta para el KO.",
          "3. Sneasler castiga el cambio con Close Combat."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Autopilot): Desperdiciar un slot ofensivo intentando usar Sucker Punch en terreno psíquico (-1.60 VP)."
      }
    ]
  },
  {
    "id": "SC-25",
    "title": "M335 Turno 2: TGT-02 Moonblast individual absorbido por Indeedee-F Follow Me",
    "driver": "Tunnel_Vision",
    "code": "TGT-02",
    "turnBadge": "TURNO 2 • EXPANDING FORCE AMENAZA • VP 4v4",
    "context": "El rival tiene a Indeedee-F (Follow Me) junto a Armarouge (Expanding Force en Terreno Psíquico). Tienes a Primarina y Garchomp en campo.",
    "oppSlots": [
      {
        "name": "Indeedee-F",
        "item": "Psychic Seed",
        "ability": "Psychic Surge",
        "hp": 100,
        "status": "Follow Me Ready"
      },
      {
        "name": "Armarouge",
        "item": "Twisted Spoon",
        "ability": "Flash Fire",
        "hp": 100,
        "status": "Expanding Force Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 100,
        "status": "Hyper Voice Ready"
      },
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Stomping Tantrum / EQ"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Primarina Hyper Voice + Garchomp Stomping Tantrum en Indeedee-F",
        "optimal": true,
        "vpDelta": "+1.65 VP",
        "log": [
          "1. Indeedee-F usa Follow Me (+2 prioridad) para absorber daño singular.",
          "2. Primarina desata Hyper Voice (Ataque de Área en base a Agua): impacta a ambos rivales, debilita a Armarouge a 20% HP potenciado por Mystic Water.",
          "3. Garchomp remata a Indeedee-F con Stomping Tantrum.",
          "4. El ataque de área ignoró la redirección y desarmó el combo rival."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): Usar ataques de área evade la trampa de Follow Me y destruye la sinergia de Expanding Force."
      },
      {
        "id": "OPT-B",
        "label": "B) Primarina Moonblast en Armarouge + Garchomp Stomping Tantrum en Armarouge",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Indeedee-F usa Follow Me: redirige ambos ataques a su propio slot.",
          "2. Moonblast choca contra Indeedee-F con poca eficacia (-24% HP).",
          "3. Stomping Tantrum choca contra Indeedee-F (-58% HP).",
          "4. Armarouge queda completamente ileso y dispara Expanding Force en área: aniquila a ambos aliados."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-02 Redirection Trap): Concentrar ataques individuales en el atacante ignorando el Follow Me cantado (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Primarina Protect + Garchomp Swords Dance",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Primarina usa Protect.",
          "2. Garchomp baila Swords Dance.",
          "3. Armarouge dispara Expanding Force sobre Garchomp (-82% HP).",
          "4. Quedas al borde de perder a tu dragón sin haber hecho daño."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Setup innecesario ante una de las combinaciones más explosivas del formato (-1.45 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Garchomp por Incineroar + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Incineroar entra al campo en seco.",
          "2. Terreno Psíquico anula su Fake Out el próximo turno.",
          "3. Cedes toda la presión ofensiva."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Autopilot): Rotación pasiva que no soluciona el Expanding Force rival (-1.50 VP)."
      }
    ]
  },
  {
    "id": "SC-26",
    "title": "M336 Turno 4: TGT-03 Overkill en Incineroar a 10% mientras Rillaboom carga Wood Hammer",
    "driver": "Tunnel_Vision",
    "code": "TGT-03",
    "turnBadge": "TURNO 4 • VP 2v2 • RECURSOS FINALES",
    "context": "Incineroar rival está a 10% HP y quemado. A su lado Rillaboom (100% HP) prepara Wood Hammer. Tienes a Charizard-Mega-Y y Kingambit.",
    "oppSlots": [
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 10,
        "status": "Burned (10% HP)"
      },
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 100,
        "status": "Wood Hammer Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Charizard-Mega-Y",
        "item": "Charizardite Y",
        "ability": "Drought",
        "hp": 85,
        "status": "Spe 167 (Sol Activo)"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 60,
        "status": "Spe 70"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard-Mega-Y Heat Wave + Kingambit Iron Head en Rillaboom",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Charizard-Mega-Y usa Heat Wave en área bajo Sol: debilita al Incineroar a 10% y deja a Rillaboom a 15% HP.",
          "2. Kingambit remata a Rillaboom con Iron Head.",
          "3. Doble KO limpio sin sufrir daño de respuesta.",
          "4. Victoria contundente."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): El ataque de área limpia el slot moribundo mientras el ataque singular neutraliza la amenaza restante."
      },
      {
        "id": "OPT-B",
        "label": "B) Charizard-Mega-Y Overheat en Incineroar + Kingambit Kowtow Cleave en Incineroar",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Overheat sobre-aniquila a Incineroar (-2 SpA drop a Charizard).",
          "2. Kowtow Cleave choca con un slot vacío.",
          "3. Rillaboom desata Wood Hammer en Kingambit y lo debilita.",
          "4. Charizard queda a -2 SpA frente a un rival aún vivo."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 Damage Overkill): Desperdiciar dos ataques y arruinar tus stats por ensañarte con un Pokémon a 10% HP (-1.80 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Charizard-Mega-Y Protect + Kingambit Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. El rival no sufre presión bajo tu Sol activo.",
          "3. Desperdicias un turno de clima favorable."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger cuando tienes el wincon en mano (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Kingambit Sucker Punch en Incineroar + Charizard Solar Beam en Incineroar",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Solar Beam y Sucker Punch se enfocan en el slot moribundo.",
          "2. Rillaboom ataca libremente a Kingambit.",
          "3. Colapso del plan de juego."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-03 / Tunnel_Vision): Ceguera de daño al concentrar todo en el objetivo equivocado (-1.60 VP)."
      }
    ]
  },
  {
    "id": "SC-27",
    "title": "M337 Turno 4: POS-03 Passive Protect abajo 2v4 en piezas vivas",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 4 • VP 2v4 • SITUACIÓN DE DESVENTAJA",
    "context": "Estás abajo 2v4 en piezas. Te quedan Primarina y Archaludon en campo frente a Garchomp e Incineroar. Necesitas remontar intercambiando KOs agresivamente.",
    "oppSlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 70,
        "status": "Spe 169"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 65,
        "status": "Spe 80"
      }
    ],
    "mySlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 70,
        "status": "Spe 80"
      },
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 80,
        "status": "Spe 105"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Primarina Moonblast en Garchomp + Archaludon Body Press en Incineroar",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Garchomp ataca con Stomping Tantrum a Archaludon (-38% HP, Stamina sube Defensa +1).",
          "2. Archaludon conecta Body Press potenciado en Incineroar (-62% HP).",
          "3. Primarina conecta Moonblast super efectivo en Garchomp: ¡KO decisivo (0% HP)!",
          "4. Eliminas al atacante más rápido del rival y equilibras el tablero a 2v3."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): En desventaja de piezas, hacer intercambios ofensivos agresivos es la única vía matemática para regresar al partido."
      },
      {
        "id": "OPT-B",
        "label": "B) Primarina Protect + Archaludon Protect",
        "optimal": false,
        "vpDelta": "-1.75 VP",
        "log": [
          "1. Ambos aliados usan Protect.",
          "2. Incineroar usa Parting Shot gratis o Garchomp usa Swords Dance (+2 Atk).",
          "3. Tu desventaja posicional se agranda sin haber cobrado nada.",
          "4. En el turno siguiente sufres una ofensiva aún más devastadora."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger pasivamente abajo 2v4 no reduce la desventaja y regala setup al rival (-1.75 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Archaludon Protect + Primarina Calm Mind",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Archaludon usa Protect.",
          "2. Primarina intenta Calm Mind.",
          "3. Garchomp ataca a Primarina con Earthquake / Stomping Tantrum (-68% HP).",
          "4. Pierdes tu principal atacante especial."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Setup codicioso cuando la situación exige daño inmediato (-1.50 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Primarina Hyper Voice + Archaludon Protect",
        "optimal": false,
        "vpDelta": "-1.35 VP",
        "log": [
          "1. Primarina ataca sola sin soporte de Archaludon.",
          "2. Incineroar y Garchomp concentran el foco en Primarina y la noquean.",
          "3. Archaludon queda solo 1v4."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Autopilot): Dividir el turno con un ataque solitario y un Protect defensivo desarticula la presión (-1.35 VP)."
      }
    ]
  },
  {
    "id": "SC-28",
    "title": "M338 Turno 2: Greed de Swords Dance con Garchomp ante Primarina Hyper Voice",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 2 • OFENSIVA EN CAMPO • VP 4v4",
    "context": "Tienes a Garchomp y Rotom-Wash en campo frente a Primarina y Archaludon. Tienes la oportunidad de noquear o presionar con ataques directos, pero te tienta usar Swords Dance.",
    "oppSlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 90,
        "status": "Hyper Voice Ready"
      },
      {
        "name": "Archaludon",
        "item": "Rocky Helmet",
        "ability": "Stamina",
        "hp": 85,
        "status": "Spe 105"
      }
    ],
    "mySlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Spe 169"
      },
      {
        "name": "Rotom-Wash",
        "item": "Sitrus Berry",
        "ability": "Levitate",
        "hp": 100,
        "status": "Spe 115"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Garchomp Stomping Tantrum en Archaludon + Rotom-Wash Thunderbolt en Primarina",
        "optimal": true,
        "vpDelta": "+1.65 VP",
        "log": [
          "1. Garchomp ataca primero con Stomping Tantrum en Archaludon (-58% HP).",
          "2. Rotom-Wash conecta Thunderbolt super efectivo en Primarina (-55% HP).",
          "3. Ambos rivales quedan gravemente dañados antes de poder castigar con eficacia.",
          "4. Tomas control total de los intercambios de daño."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): Ofensiva directa y equilibrada que castiga las debilidades del rival sin perder turnos en setup innecesario."
      },
      {
        "id": "OPT-B",
        "label": "B) Garchomp Swords Dance + Rotom-Wash Protect",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Rotom-Wash usa Protect.",
          "2. Garchomp usa Swords Dance (+2 Atk).",
          "3. Primarina desata Moonblast / Hyper Voice super efectivo sobre Garchomp: ¡OHKO devastador!",
          "4. Garchomp cae debilitado habiendo ganado +2 de ataque que jamás llegó a utilizar."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Buscar boosts codiciosos frente a atacantes con cobertura super efectiva cuesta a tu sweeper principal (-1.80 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Garchomp Protect + Rotom-Wash Protect",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. Primarina y Archaludon no reciben presión.",
          "3. Cedes la iniciativa del turno."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger sin motivo frente a dos objetivos en rango de daño favorable (-1.25 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Garchomp Dragon Claw en Primarina + Rotom-Wash Will-O-Wisp en Archaludon",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Dragon Claw no hace daño a Primarina (inmunidad de tipo Hada)!",
          "2. Rotom quema a Archaludon pero su daño es principalmente especial.",
          "3. Desperdicio grave de un turno de ataque."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Autopilot): Lanzar movimientos de tipo Dragón a Pokémon de tipo Hada (-1.45 VP)."
      }
    ]
  },
  {
    "id": "SC-29",
    "title": "M339 Turno 1: SPD-01 No Mega Evolucionar a Lucario para guardar sorpresa",
    "driver": "Greed",
    "code": "SPD-01",
    "turnBadge": "TURNO 1 • LEAD BATTLE • VP 4v4",
    "context": "Abres con Lucario (Lucarionite) y Farigiraf frente a Garchomp (Spe 169) e Incineroar. Decides no activar la Mega Evolución de Lucario creyendo que puedes 'guardar la sorpresa'.",
    "oppSlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Spe 169"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Spe 80"
      }
    ],
    "mySlots": [
      {
        "name": "Lucario",
        "item": "Lucarionite",
        "ability": "Inner Focus",
        "hp": 100,
        "status": "Spe 156 (Base 90)"
      },
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 100,
        "status": "Spe 80"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Mega Evolucionar Lucario y usar Close Combat en Incineroar + Farigiraf Trick Room",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Lucario Mega Evoluciona: su velocidad escala instantáneamente a 180 Spe (+11 sobre Garchomp)!",
          "2. Lucario se mueve primero y conecta Close Combat potenciado por Adaptability en Incineroar: ¡OHKO!",
          "3. Garchomp ataca a Farigiraf (-48% HP).",
          "4. Farigiraf castea Trick Room o ataca con Psychic."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): En Regulation M-C la Mega Evolución recalcula la velocidad al instante, superando a Garchomp de inmediato."
      },
      {
        "id": "OPT-B",
        "label": "B) No Mega Evolucionar y usar Close Combat con Lucario Base + Farigiraf Psychic en Garchomp",
        "optimal": false,
        "vpDelta": "-1.90 VP",
        "log": [
          "1. Lucario permanece en su forma base (Spe 156).",
          "2. Garchomp (Spe 169) se mueve antes que Lucario y desata Earthquake.",
          "3. Lucario base recibe OHKO antes de poder atacar.",
          "4. Pierdes a tu Mega en Turno 1 sin haber conectado un solo golpe."
        ],
        "verdict": "❌ FUGA TÁCTICA (SPD-01 Activation Phase Blindness): No Mega Evolucionar te deja en 156 Spe, siendo superado y debilitado por Garchomp (-1.90 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Lucario Protect + Farigiraf Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. Cedes la iniciativa en turno 1 sin verificar velocidad.",
          "3. El rival posiciona a sus piezas sin presión."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Desperdiciar el turno 1 de tu Mega con un Protect reactivo (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Lucario por Rillaboom en seco + Farigiraf Trick Room",
        "optimal": false,
        "vpDelta": "-1.55 VP",
        "log": [
          "1. Rotas a Lucario recibiendo daño directo de Garchomp.",
          "2. Rillaboom queda debilitado o muy tocado.",
          "3. Desperdicio de ventaja de matchup."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar en seco cuando tenías superioridad de velocidad activa (-1.55 VP)."
      }
    ]
  },
  {
    "id": "SC-30",
    "title": "M340 Turno 2: MEC-01 Will-O-Wisp hacia Armarouge activando Flash Fire",
    "driver": "Greed",
    "code": "MEC-01",
    "turnBadge": "TURNO 2 • MECÁNICA DE HABILIDAD • VP 4v4",
    "context": "Armarouge rival y Indeedee-F están en campo. Tienes a Incineroar y Garchomp. Deseas neutralizar el daño físico del rival y consideras usar Will-O-Wisp hacia Armarouge.",
    "oppSlots": [
      {
        "name": "Armarouge",
        "item": "Twisted Spoon",
        "ability": "Flash Fire",
        "hp": 100,
        "status": "Flash Fire Inactivo"
      },
      {
        "name": "Indeedee-F",
        "item": "Psychic Seed",
        "ability": "Psychic Surge",
        "hp": 90,
        "status": "Follow Me Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Knock Off Ready"
      },
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Stomping Tantrum Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Knock Off en Armarouge + Garchomp Stomping Tantrum en Indeedee-F",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Incineroar usa Knock Off super efectivo sobre Armarouge: le retira su Twisted Spoon y causa -52% HP.",
          "2. Garchomp conecta Stomping Tantrum en Indeedee-F (-68% HP).",
          "3. Neutralizas la potencia ofensiva del rival sin activar habilidades contraproducentes.",
          "4. Posición dominante."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Ataques de daño directo que remueven objetos y evitan alimentar la habilidad Flash Fire de Armarouge."
      },
      {
        "id": "OPT-B",
        "label": "B) Incineroar Will-O-Wisp en Armarouge + Garchomp Swords Dance",
        "optimal": false,
        "vpDelta": "-1.95 VP",
        "log": [
          "1. Incineroar usa Will-O-Wisp sobre Armarouge.",
          "2. ¡Armarouge absorbe el fuego gracias a Flash Fire! Sus ataques de tipo Fuego aumentan un 50% de potencia.",
          "3. Armarouge responde con Armor Cannon bajo Flash Fire: destruye a Garchomp de un solo golpe.",
          "4. Convertiste al atacante rival en una máquina de KOs imparable."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Mechanics / Flash Fire): Lanzar Will-O-Wisp a un Pokémon con Flash Fire no lo quema y potencia sus ataques 50% (-1.95 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Incineroar Protect + Garchomp Protect",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. El rival mantiene el campo psíquico intacto.",
          "3. Sin progreso táctico."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger sin amenazar el núcleo rival (-1.25 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Incineroar Flare Blitz en Armarouge + Garchomp Protect",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Flare Blitz golpea a Armarouge y activa Flash Fire una vez más.",
          "2. Armarouge queda inmune y potenciado.",
          "3. Falla mecánica grave."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Autopilot): Atacar con Fuego a un Pokémon de Fuego con Flash Fire (-1.80 VP)."
      }
    ]
  },
  {
    "id": "SC-31",
    "title": "M341 Turno 3: Greed de Calm Mind Primarina ante Archaludon Electro Shot en Lluvia",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 3 • LLUVIA ACTIVA • VP 3v3",
    "context": "Lluvia activa en campo. Archaludon rival prepara Electro Shot (carga instantánea en lluvia). A su lado Pelipper. Tienes a Primarina y Kingambit.",
    "oppSlots": [
      {
        "name": "Archaludon",
        "item": "Rocky Helmet",
        "ability": "Stamina",
        "hp": 90,
        "status": "Electro Shot Ready (Lluvia)"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 70,
        "status": "Rain 3T"
      }
    ],
    "mySlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 85,
        "status": "Spe 80"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 95,
        "status": "Spe 70"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Kingambit Kowtow Cleave en Archaludon + Primarina Moonblast en Pelipper",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Kingambit conecta Kowtow Cleave en Archaludon (-38% HP).",
          "2. Primarina desata Moonblast super efectivo sobre Pelipper y lo debilita (0% HP).",
          "3. Archaludon usa Electro Shot pero cae el setter de lluvia.",
          "4. La amenaza climática queda desmantelada."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Concentrar daño en el setter de lluvia elimina la fuente de poder del Electro Shot rival."
      },
      {
        "id": "OPT-B",
        "label": "B) Primarina Calm Mind + Kingambit Protect",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Kingambit usa Protect.",
          "2. Primarina intenta Calm Mind (+1 SpA/+1 SpD).",
          "3. Archaludon ejecuta Electro Shot instantáneo en lluvia: golpe super efectivo masivo que pulveriza a Primarina.",
          "4. El boost de +1 SpD no fue suficiente para sobrevivir al ataque eléctrico con STAB en lluvia."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Usar movimientos de setup ante un ataque super efectivo instantáneo de 130 de potencia base (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Primarina Protect + Kingambit Protect",
        "optimal": false,
        "vpDelta": "-1.20 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. La lluvia continúa activa.",
          "3. Cedes un turno sin castigar."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Retrasar el turno sin alterar las condiciones del partido (-1.20 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Primarina por Rillaboom en seco + Kingambit Kowtow Cleave en Archaludon",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Rillaboom entra en seco y recibe Hurricane de Pelipper (-65% HP).",
          "2. Kingambit ataca a Archaludon.",
          "3. Rillaboom queda incapacitado."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar a un tipo Planta directo ante el Hurricane de Pelipper (-1.50 VP)."
      }
    ]
  },
  {
    "id": "SC-32",
    "title": "M342 Turno 1: Nasty Plot con Gengar-Mega en vez de cantar Perish Song o atacar",
    "driver": "Greed",
    "code": "SPD-01",
    "turnBadge": "TURNO 1 • SHADOW TAG LOCK • VP 4v4",
    "context": "Abres con Gengar-Mega y Incineroar frente a Primarina y Kingambit. Tienes a ambos rivales atrapados bajo Shadow Tag. Te tienta boostearte con Nasty Plot.",
    "oppSlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 100,
        "status": "Atrapado por Shadow Tag"
      },
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 100,
        "status": "Atrapado por Shadow Tag"
      }
    ],
    "mySlots": [
      {
        "name": "Gengar-Mega",
        "item": "Gengarite",
        "ability": "Shadow Tag",
        "hp": 100,
        "status": "Spe 200 (Post-Mega)"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Fake Out Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Fake Out en Kingambit + Gengar-Mega Sludge Bomb en Primarina",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Incineroar usa Fake Out en Kingambit: Kingambit retrocede y no puede usar Sucker Punch ni Kowtow Cleave.",
          "2. Gengar-Mega desata Sludge Bomb super efectivo sobre Primarina: ¡OHKO limpio!",
          "3. Desactivas al atacante peligroso y aseguras el primer KO del partido.",
          "4. Ventaja táctica contundente."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Bloquear la amenaza con Fake Out y ejecutar el KO garantizado con el atacante rápido consolida el control de la mesa."
      },
      {
        "id": "OPT-B",
        "label": "B) Gengar-Mega Nasty Plot + Incineroar Parting Shot en Primarina",
        "optimal": false,
        "vpDelta": "-1.90 VP",
        "log": [
          "1. Gengar-Mega usa Nasty Plot (+2 SpA).",
          "2. Kingambit ejecuta Kowtow Cleave directo sobre Gengar-Mega: ¡OHKO masivo!",
          "3. Gengar-Mega cae debilitado en turno 1 sin haber atacado.",
          "4. Pierdes tu Mega Evolución y el bloqueo de Shadow Tag por buscar un boost codicioso."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Usar Nasty Plot frente a Kingambit sin mitigar su daño físico destruye tu condición de victoria (-1.90 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Gengar-Mega Protect + Incineroar Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect pasivo en turno 1.",
          "2. Desperdicias la ventana de Fake Out de Incineroar.",
          "3. El rival prepara sus jugadas con calma."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Quemar el turno 1 de Fake Out con Protect pasivo (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Gengar-Mega Shadow Ball en Kingambit + Incineroar Flare Blitz en Primarina",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Shadow Ball es resistido por Kingambit (tipo Siniestro/Acero).",
          "2. Flare Blitz hace daño neutro a Primarina pero recibe recoil alto.",
          "3. Mal aprovechamiento de ventajas de tipo."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Autopilot): Lanzar movimientos resistidos a los slots equivocados (-1.60 VP)."
      }
    ]
  },
  {
    "id": "SC-33",
    "title": "M343 Turno 3: POS-01 Dry Hard Switch por Tilt tras sufrir Golpe Crítico",
    "driver": "Tilt",
    "code": "POS-01",
    "turnBadge": "TURNO 3 • RESPUESTA EMOCIONAL • VP 3v3",
    "context": "En el turno anterior el rival conectó un golpe crítico inesperado contra tu lead. Sientes frustración y decides rotar en seco apresuradamente.",
    "oppSlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 85,
        "status": "Spe 169"
      },
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 70,
        "status": "Close Combat Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Archaludon",
        "item": "Rocky Helmet",
        "ability": "Stamina",
        "hp": 65,
        "status": "Spe 105"
      },
      {
        "name": "Rotom-Wash",
        "item": "Sitrus Berry",
        "ability": "Levitate",
        "hp": 90,
        "status": "Will-O-Wisp Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rotom-Wash Will-O-Wisp en Garchomp + Archaludon Body Press en Sneasler",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Rotom-Wash aplica Will-O-Wisp sobre Garchomp: reduce su ataque físico un 50% y anula su peligro.",
          "2. Sneasler intenta Close Combat pero Archaludon resiste y activa Stamina.",
          "3. Archaludon conecta Body Press en Sneasler y lo deja a 1 HP.",
          "4. Mantienes la compostura y neutralizas la ofensiva rival de raíz."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Mantener la disciplina mental tras un mal evento y ejecutar el control de daño asegura la estabilidad del tablero."
      },
      {
        "id": "OPT-B",
        "label": "B) Cambiar Archaludon por Incineroar en seco + Rotom-Wash Hydro Pump en Garchomp",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Retiras a Archaludon por impulso emocional → Entra Incineroar en seco.",
          "2. Garchomp usa Stomping Tantrum en el slot entrante: ¡OHKO super efectivo demoledor!",
          "3. Incineroar cae sin actuar.",
          "4. Regalaste una segunda pieza por reaccionar con frustración."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Tilt): Cambiar en seco por impulso emocional regala una ventaja irrecuperable al oponente (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Rotom-Wash Protect + Archaludon Protect",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Doble Protect de frustración.",
          "2. Los atacantes rivales mantienen su potencia intacta.",
          "3. No resuelves la amenaza física en mesa."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Tilt): Proteger por miedo tras un golpe crítico no repara el daño recibido (-1.25 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Archaludon Flash Cannon en Garchomp + Rotom-Wash Volt Switch en Sneasler",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Volt Switch no hace suficiente daño a Sneasler.",
          "2. Garchomp ataca con Stomping Tantrum y causa daño severo.",
          "3. Foco disperso sin control de estado."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Tilt): Atacar a ciegas sin mitigar el ataque de Garchomp (-1.45 VP)."
      }
    ]
  },
  {
    "id": "SC-34",
    "title": "M344 Turno 4: TGT-01 Atacar con rabia al slot que acaba de debilitar a tu compañero",
    "driver": "Tilt",
    "code": "TGT-01",
    "turnBadge": "TURNO 4 • FOCO EMOCIONAL • VP 2v2",
    "context": "Kingambit rival acaba de debilitar a tu Incineroar y sabes que su jugada estándar ahora es Protect. Sientes ira hacia ese slot y quieres atacarlo con todo.",
    "oppSlots": [
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 40,
        "status": "Protect Telegrafiado"
      },
      {
        "name": "Dragonite",
        "item": "Lum Berry",
        "ability": "Multiscale",
        "hp": 85,
        "status": "Extreme Speed Ready"
      }
    ],
    "mySlots": [
      {
        "name": "Lucario-Mega",
        "item": "Lucarionite",
        "ability": "Adaptability",
        "hp": 90,
        "status": "Spe 180"
      },
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 70,
        "status": "Spe 80"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Lucario-Mega Meteor Mash en Dragonite + Primarina Moonblast en Dragonite",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Kingambit usa Protect! Absorbe el aire del slot izquierdo.",
          "2. Lucario-Mega ataca a Dragonite con Meteor Mash rompiendo Multiscale (-50% HP).",
          "3. Primarina conecta Moonblast super efectivo en Dragonite y lo debilita por completo.",
          "4. Kingambit queda solo frente a tus dos atacantes."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Castigar al compañero vulnerable en lugar de buscar venganza contra el slot con Protect asegura la victoria."
      },
      {
        "id": "OPT-B",
        "label": "B) Lucario-Mega Close Combat en Kingambit + Primarina Hyper Voice en Kingambit",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Kingambit usa Protect: bloquea ambos ataques con facilidad.",
          "2. Close Combat de Lucario se estrella contra Protect.",
          "3. Dragonite usa Extreme Speed con STAB en Lucario (-50% HP).",
          "4. Desperdicias tu turno más importante por atacar al objetivo equivocado."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Revenge Protect Tunneling): Atacar con rabia al Pokémon que tiene Protect cantado regala el turno al rival (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Lucario-Mega Protect + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. Kingambit y Dragonite mantienen control del campo.",
          "3. Sin ventaja de tablero."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger sin construir un intercambio favorable (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Primarina Protect + Lucario-Mega Swords Dance",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Lucario intenta Swords Dance.",
          "2. Dragonite golpea con Extreme Speed y Kingambit contraataca el turno siguiente.",
          "3. Riesgo de KO innecesario."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Setup cuando tenías el KO disponible sobre Dragonite (-1.50 VP)."
      }
    ]
  },
  {
    "id": "SC-35",
    "title": "M345 Turno 2: Overprediction de doble cambio usando ataques de cobertura débiles",
    "driver": "Tilt",
    "code": "TGT-01",
    "turnBadge": "TURNO 2 • OVERPREDICTION • VP 4v4",
    "context": "El rival tiene a Pelipper y Basculegion en lluvia. Tienes a Rillaboom y Archaludon. Asumes que el rival 'obviamente' va a cambiar a sus dos slots y quieres castigar a los Pokémon entrantes.",
    "oppSlots": [
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 90,
        "status": "Rain Active"
      },
      {
        "name": "Basculegion-M",
        "item": "Life Orb",
        "ability": "Swift Swim",
        "hp": 100,
        "status": "Swift Swim Active"
      }
    ],
    "mySlots": [
      {
        "name": "Rillaboom",
        "item": "Miracle Seed",
        "ability": "Grassy Surge",
        "hp": 100,
        "status": "Grassy Glide Ready"
      },
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 100,
        "status": "Electro Shot Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Grassy Glide en Basculegion + Archaludon Electro Shot en Pelipper",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Rillaboom ataca con Grassy Glide con prioridad a Basculegion (-74% HP).",
          "2. El rival no cambió: ejecutó sus ataques planeados.",
          "3. Archaludon desata Electro Shot en Pelipper y lo debilita.",
          "4. Juegas la línea matemáticamente óptima sin caer en la trampa de la sobre-predicción."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Ejecutar la línea minimax más sólida castiga al rival tanto si se queda como si cambia, sin asumir riesgos absurdos."
      },
      {
        "id": "OPT-B",
        "label": "B) Rillaboom Knock Off en slot vacío + Archaludon Flash Cannon en slot vacío",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Asumes un doble cambio del rival y usas ataques secundarios.",
          "2. El rival NO cambia y se queda en campo atacando con todo.",
          "3. Basculegion desata Wave Crash y Pelipper lanza Hurricane: destruyen tu posición.",
          "4. Pierdes el partido por sobre-pensar una jugada evidente."
        ],
        "verdict": "❌ FUGA TÁCTICA (TGT-01 Overprediction): Intentar predecir un doble cambio imaginario cuando tenías la jugada óptima directa (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Rillaboom Protect + Archaludon Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect pasivo por indecisión.",
          "2. El rival sigue controlando la lluvia libremente.",
          "3. Pierdes un turno de iniciativa."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Tilt): Parálisis por análisis ejecutando Protect pasivo (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Rillaboom por Incineroar + Archaludon Protect",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. Traes a Incineroar en seco ante lluvia activa.",
          "2. Basculegion lo noquea con Wave Crash.",
          "3. Error garrafal de cambio."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambiar a un tipo Fuego en lluvia activa (-1.60 VP)."
      }
    ]
  },
  {
    "id": "SC-36",
    "title": "M346 Turno 3: POS-03 Protect consecutivo desesperado (33% de éxito)",
    "driver": "Tilt",
    "code": "POS-03",
    "turnBadge": "TURNO 3 • DECISIÓN DE VARIANZA • VP 2v2",
    "context": "Kingambit usó Protect el turno anterior con éxito y le queda 30% HP. Sientes desesperación y te tienta clickear Protect por segundo turno consecutivo.",
    "oppSlots": [
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 75,
        "status": "Spe 169"
      },
      {
        "name": "Charizard-Mega-Y",
        "item": "Charizardite Y",
        "ability": "Drought",
        "hp": 80,
        "status": "Sol Activo"
      }
    ],
    "mySlots": [
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 30,
        "status": "Protect usado en T2"
      },
      {
        "name": "Rotom-Wash",
        "item": "Sitrus Berry",
        "ability": "Levitate",
        "hp": 85,
        "status": "Hydro Pump Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Kingambit Sucker Punch en Charizard + Rotom-Wash Hydro Pump en Garchomp",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Kingambit conecta Sucker Punch con prioridad antes de que Charizard ataque (-52% HP).",
          "2. Rotom-Wash dispara Hydro Pump sobre Garchomp y lo debilita.",
          "3. Aunque Kingambit caiga ante el contraataque, cobraste daño clave y eliminaste a un rival.",
          "4. Quedas en posición ganadora 1v1 con ventaja de matchup."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Aceptar el intercambio y asegurar daño con prioridad en vez de depender de la baja probabilidad de un Protect consecutivo."
      },
      {
        "id": "OPT-B",
        "label": "B) Intentar Protect consecutivo con Kingambit + Rotom-Wash Protect",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Kingambit intenta Protect consecutivo: ¡El movimiento FALLA (solo 33% de éxito)! ",
          "2. Charizard-Mega-Y ejecuta Heat Wave bajo Sol y debilita a Kingambit sin resistencia.",
          "3. Rotom-Wash queda solo y superado en números.",
          "4. Perdiste tu recurso por confiar en el azar de la desesperación."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Tilt / Desperation Protect): El Protect consecutivo tiene solo 33% de éxito; jugar a la lotería en vez de intercambiar daño destruye tu equity (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Kingambit Kowtow Cleave en Garchomp + Rotom-Wash Protect",
        "optimal": false,
        "vpDelta": "-1.45 VP",
        "log": [
          "1. Garchomp ataca primero por orden de velocidad antes del Kowtow Cleave.",
          "2. Kingambit cae sin atacar por falta de prioridad.",
          "3. Rotom-Wash queda aislado."
        ],
        "verdict": "❌ FUGA TÁCTICA (SPD-01 Autopilot): No usar el movimiento de prioridad cuando tu Pokémon no tiene suficiente velocidad para actuar (-1.45 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Rotom-Wash por banca en seco + Kingambit Sucker Punch en Charizard",
        "optimal": false,
        "vpDelta": "-1.60 VP",
        "log": [
          "1. El cambio entra recibiendo daño del Heat Wave rival.",
          "2. Kingambit conecta pero no es suficiente sin el apoyo de Rotom.",
          "3. Colapso del tablero."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambio seco innecesario en situación crítica (-1.60 VP)."
      }
    ]
  },
  {
    "id": "SC-37",
    "title": "M347 Turno 1: Rushing Execution clickeando en segundo 42 sin revisar checklist",
    "driver": "Tilt",
    "code": "POS-02",
    "turnBadge": "TURNO 1 • APRESURAMIENTO • VP 4v4",
    "context": "Empieza el combate. El rival lidera con Sneasler e Incineroar. Tienes a Farigiraf y Primarina. Por prisa o nerviosismo clickeas tu primer impulso antes de revisar el tablero.",
    "oppSlots": [
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 100,
        "status": "Fake Out / Dire Claw"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Fake Out / Knock Off"
      }
    ],
    "mySlots": [
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 100,
        "status": "Armor Tail Activo"
      },
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 100,
        "status": "Hyper Voice Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Farigiraf Trick Room + Primarina Moonblast en Sneasler",
        "optimal": true,
        "vpDelta": "+1.75 VP",
        "log": [
          "1. Incineroar y Sneasler intentan Fake Out pero Armor Tail de Farigiraf bloquea toda prioridad rival!",
          "2. Primarina Moonblast impacta en Sneasler y rompe su Focus Sash (1% HP).",
          "3. Farigiraf castea Trick Room exitosamente.",
          "4. Tomas control absoluto de la velocidad para los próximos 4 turnos."
        ],
        "verdict": "✅ ÓPTIMO (+1.75 VP): Revisar la habilidad de tu lead (Armor Tail bloquea Fake Out) te permite ejecutar Trick Room con total impunidad."
      },
      {
        "id": "OPT-B",
        "label": "B) Click apresurado: Farigiraf Psychic en Incineroar + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Clickeas en 3 segundos sin pensar: Farigiraf usa Psychic hacia Incineroar.",
          "2. ¡Incineroar es tipo Siniestro y es totalmente INMUNE al tipo Psíquico!",
          "3. El movimiento no tiene efecto.",
          "4. Incineroar conecta Knock Off en Farigiraf (-68% HP) y Sneasler presiona a Primarina."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-02 / Tilt Rushing): Atacar a un tipo Siniestro con ataques Psíquicos por apresurarse sin aplicar el checklist (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Farigiraf Protect + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect innecesario.",
          "2. Desperdicias la inmunidad a Fake Out que te daba Armor Tail.",
          "3. Pierdes un turno de setup gratis."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger cuando tu habilidad ya te hacía inmune al Fake Out rival (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Farigiraf por Rillaboom en seco + Primarina Moonblast en Incineroar",
        "optimal": false,
        "vpDelta": "-1.55 VP",
        "log": [
          "1. Retiras a Farigiraf y pierdes la protección de Armor Tail.",
          "2. Sneasler conecta Fake Out en Primarina y la hace retroceder.",
          "3. El rival se apodera del turno 1."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Autopilot): Quitar a Farigiraf reactiva los Fake Out rivales contra tu atacante (-1.55 VP)."
      }
    ]
  },
  {
    "id": "SC-38",
    "title": "M348 Turno 2: MEC-02 Exponer a Talonflame a Sucker Punch en Terreno Psíquico",
    "driver": "Format_Divergence",
    "code": "MEC-02",
    "turnBadge": "TURNO 2 • MECÁNICA DE TERRENO • VP 3v3",
    "context": "Terreno Psíquico activo en mesa. Kingambit rival (Sucker Punch) está frente a tu Charizard-Mega-Y (Volador) y Farigiraf. Crees erróneamente que el Terreno Psíquico protege a Charizard de la prioridad.",
    "oppSlots": [
      {
        "name": "Kingambit",
        "item": "Black Glasses",
        "ability": "Defiant",
        "hp": 75,
        "status": "Sucker Punch Listo"
      },
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 80,
        "status": "Spe 105"
      }
    ],
    "mySlots": [
      {
        "name": "Charizard-Mega-Y",
        "item": "Charizardite Y",
        "ability": "Drought",
        "hp": 45,
        "status": "Volador (Airborne)"
      },
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 85,
        "status": "Armor Tail Activo"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard-Mega-Y Protect + Farigiraf Hyper Voice",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Charizard usa Protect! Bloquea de forma segura cualquier ataque dirigido.",
          "2. Kingambit intenta atacar pero es mitigado.",
          "3. Farigiraf desgasta a ambos rivales con Hyper Voice.",
          "4. Preservas a tu Mega ileso para castigar el siguiente turno."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Reconocer que los Pokémon voladores NO están protegidos por el Terreno Psíquico te permite proteger a Charizard adecuadamente."
      },
      {
        "id": "OPT-B",
        "label": "B) Charizard-Mega-Y Heat Wave sin proteger + Farigiraf Psychic en Archaludon",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Asumes que el Terreno Psíquico bloquea prioridades hacia Charizard y atacas directamente.",
          "2. ¡Charizard es tipo Volador y NO toca el suelo (Airborne Ground Exemption)! El Terreno Psíquico NO lo protege.",
          "3. Kingambit usa Sucker Punch (+1 prioridad) sobre Charizard: golpe fulminante que lo debilita (0% HP).",
          "4. Pierdes a tu Mega por desconocer las reglas mecánicas del terreno."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-02 Airborne Ground Exemption): Los Pokémon tipo Volador o con Levitate no reciben protección de prioridad en Terreno Psíquico (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Farigiraf Protect + Charizard-Mega-Y Roost",
        "optimal": false,
        "vpDelta": "-1.40 VP",
        "log": [
          "1. Intentas curarte con Roost en vez de presionar.",
          "2. Kingambit y Archaludon concentran fuego sobre Charizard.",
          "3. Pierdes tempo defensivo."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Play): Curarse pasivamente en vez de atacar o proteger (-1.40 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Charizard por Garchomp en seco + Farigiraf Psychic",
        "optimal": false,
        "vpDelta": "-1.55 VP",
        "log": [
          "1. Garchomp entra en seco recibiendo daño de Kingambit.",
          "2. Comprometes la salud de tu atacante físico.",
          "3. Desventaja de rotación."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Dry Hard Switch): Cambio en seco no forzado (-1.55 VP)."
      }
    ]
  },
  {
    "id": "SC-39",
    "title": "M349 Turno 1: SPD-01 Creer que la velocidad de Mega Evolución aplica al turno siguiente",
    "driver": "Format_Divergence",
    "code": "SPD-01",
    "turnBadge": "TURNO 1 • REGLAS REGULATION M-C • VP 4v4",
    "context": "Tienes a Charizard (Charizardite Y) e Incineroar frente a Sneasler y Lucario. En formatos pre-Gen 7 las Megas no recalculaban velocidad el mismo turno; dudas sobre cuándo aplica el orden.",
    "oppSlots": [
      {
        "name": "Lucario",
        "item": "Life Orb",
        "ability": "Inner Focus",
        "hp": 100,
        "status": "Spe 156"
      },
      {
        "name": "Sneasler",
        "item": "Focus Sash",
        "ability": "Unburden",
        "hp": 100,
        "status": "Spe 189"
      }
    ],
    "mySlots": [
      {
        "name": "Charizard",
        "item": "Charizardite Y",
        "ability": "Solar Power",
        "hp": 100,
        "status": "Spe 167 (Post-Mega)"
      },
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Fake Out Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Fake Out en Sneasler + Mega Evolucionar Charizard y usar Heat Wave",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Incineroar usa Fake Out en Sneasler anulando su turno.",
          "2. Charizard Mega Evoluciona: Drought activa el Sol y su velocidad se aplica en este mismo turno.",
          "3. Charizard supera a Lucario (167 Spe vs 156 Spe) y desata Heat Wave bajo Sol: KO masivo a Lucario.",
          "4. El recálculo instantáneo asegura el KO antes de que Lucario pueda actuar."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): En Regulation M-C la velocidad tras la Mega Evolución se recalcula de inmediato en la fase activa del turno."
      },
      {
        "id": "OPT-B",
        "label": "B) Charizard Protect por miedo a que Lucario sea más rápido este turno + Incineroar Flare Blitz",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Crees erróneamente que la velocidad de Mega no aplica en el turno de evolución y usas Protect pasivo.",
          "2. Incineroar ataca solo y recibe daño severo de Sneasler.",
          "3. Desperdicias la ventana de ataque con Sol de tu Mega en Turno 1.",
          "4. Cedes la iniciativa sin motivo mecánico."
        ],
        "verdict": "❌ FUGA TÁCTICA (SPD-01 Format Divergence): Asumir mecánicas obsoletas de velocidad retrasa tu ofensiva y regala turnos (-1.80 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Doble Protect pasivo (Charizard Protect + Incineroar Protect)",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. El rival no gasta recursos.",
          "3. Malgasto del turno de Fake Out."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger sin generar ventaja de posición (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Cambiar Charizard por Rillaboom en seco + Incineroar Parting Shot",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Rotación innecesaria en Turno 1.",
          "2. Rillaboom recibe daño de entrada.",
          "3. Pérdida de tempo ofensivo."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-01 Autopilot): Rotar en seco en turno 1 teniendo ventaja de matchups directos (-1.50 VP)."
      }
    ]
  },
  {
    "id": "SC-40",
    "title": "M350 Turno 1: [ILLEGAL_FORMAT_SPECIES] Intento de uso de Amoonguss o Urshifu",
    "driver": "Format_Divergence",
    "code": "MEC-01",
    "turnBadge": "TURNO 1 • LEGALIDAD REGULATION M-C • VP 4v4",
    "context": "Estás planificando la selección de 4 Pokémon ante un equipo con Trick Room. Te tienta traer a Amoonguss con Spore o Urshifu para romper Protects, olvidando las restricciones de especies del formato.",
    "oppSlots": [
      {
        "name": "Farigiraf",
        "item": "Mental Herb",
        "ability": "Armor Tail",
        "hp": 100,
        "status": "Trick Room Setter"
      },
      {
        "name": "Torkoal",
        "item": "Charcoal",
        "ability": "Drought",
        "hp": 100,
        "status": "Erupción bajo TR"
      }
    ],
    "mySlots": [
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 100,
        "status": "Legal en Reg M-C"
      },
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 100,
        "status": "Legal en Reg M-C"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Knock Off en Farigiraf + Primarina Hyper Voice en área",
        "optimal": true,
        "vpDelta": "+1.65 VP",
        "log": [
          "1. Incineroar ejecuta Knock Off sobre Farigiraf: remueve su Mental Herb y genera daño super efectivo (-44% HP).",
          "2. Primarina desata Hyper Voice en área: presiona a ambos slots rivales.",
          "3. Usas piezas 100% legales del pool verificado de Regulation M-C para controlar la mesa.",
          "4. Plan de juego legal y efectivo."
        ],
        "verdict": "✅ ÓPTIMO (+1.65 VP): Apoyarse exclusivamente en el pool verificado de Regulation M-C y presionar con herramientas legales del formato."
      },
      {
        "id": "OPT-B",
        "label": "B) Asumir presencia de Amoonguss con Spore o Urshifu para ignorar Protect",
        "optimal": false,
        "vpDelta": "-2.00 VP",
        "log": [
          "1. Intentas planificar la partida alrededor de Amoonguss o Urshifu.",
          "2. ¡[ILLEGAL_FORMAT_SPECIES] Amoonguss y Urshifu están PERMANENTEMENTE BANEADOS en Regulation M-C!",
          "3. El simulador oficial rechaza la jugada por contaminación de formatos ajenos.",
          "4. Tu plan de juego colapsa al basarse en especies no permitidas."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Illegal Format Species): Amoonguss y Urshifu son ilegales en Regulation M-C; planificar con ellos constituye un error crítico (-2.00 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Doble Protect pasivo en turno 1",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. Farigiraf castea Trick Room libremente.",
          "3. Quedas bajo Trick Room rival sin haber hecho nada."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Permitir Trick Room gratis sin disputar el turno (-1.25 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Rendir el turno esperando a ver qué hace el rival",
        "optimal": false,
        "vpDelta": "-1.80 VP",
        "log": [
          "1. Cedes la iniciativa por falta de conocimiento de la lista de especies.",
          "2. El rival establece su condición de victoria sin oposición.",
          "3. Partida perdida."
        ],
        "verdict": "❌ FUGA TÁCTICA (Tilt / Autopilot): Inacción por duda de formato (-1.80 VP)."
      }
    ]
  },
  {
    "id": "SC-41",
    "title": "M351 Turno 2: Asumir Assault Vest o Safety Goggles en el rival",
    "driver": "Format_Divergence",
    "code": "MEC-01",
    "turnBadge": "TURNO 2 • LEGALIDAD DE OBJETOS • VP 4v4",
    "context": "Te enfrentas a un Archaludon rival y calculas tu daño asumiendo que lleva Assault Vest o Safety Goggles, objetos restringidos o ausentes en Regulation_MC_Items.csv.",
    "oppSlots": [
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 100,
        "status": "Leftovers Legal"
      },
      {
        "name": "Pelipper",
        "item": "Damp Rock",
        "ability": "Drizzle",
        "hp": 100,
        "status": "Damp Rock Legal"
      }
    ],
    "mySlots": [
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 100,
        "status": "Spe 80"
      },
      {
        "name": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "hp": 100,
        "status": "Spe 169"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Primarina Hyper Voice + Garchomp Stomping Tantrum en Archaludon",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Conocer la lista legal de objetos te permite saber que Archaludon no tiene bonificación de defensa especial por Assault Vest.",
          "2. Primarina desata Hyper Voice causando daño masivo a Archaludon (-48% HP).",
          "3. Garchomp remata con Stomping Tantrum super efectivo (0% HP KO).",
          "4. Eliminas al peligro principal en un solo turno."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Calibrar tus cálculos con la lista estricta de objetos legales de Regulation M-C garantiza decisiones certeras."
      },
      {
        "id": "OPT-B",
        "label": "B) Asumir que Archaludon tiene Assault Vest y evitar atacarlo con daño especial",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Asumes erróneamente un bulk especial inflado por un objeto no legal.",
          "2. Evitas usar Hyper Voice y lanzas ataques físicos de bajo impacto que solo activan Stamina.",
          "3. Archaludon sube su Defensa a +2 y se vuelve inexpugnable.",
          "4. El rival barre con Body Press en los siguientes turnos."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Prohibited Item Assumption): Calcular daños asumiendo objetos fuera del reglamento deforma la toma de decisiones (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Primarina Protect + Garchomp Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Doble Protect pasivo por duda.",
          "2. Archaludon se posiciona y Pelipper mantiene lluvia.",
          "3. Cedes un turno crucial."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Proteger por desconfianza en los rangos de daño (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Garchomp Swords Dance + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.50 VP",
        "log": [
          "1. Buscas setup innecesario.",
          "2. Archaludon te ataca con Draco Meteor.",
          "3. Pérdida severa de salud."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Greed): Setup codicioso basado en premisas falsas (-1.50 VP)."
      }
    ]
  },
  {
    "id": "SC-42",
    "title": "M352 Turno 3: MEC-01 Prankster Taunt de Whimsicott hacia Incineroar (Tipo Siniestro)",
    "driver": "Format_Divergence",
    "code": "MEC-01",
    "turnBadge": "TURNO 3 • INMUNIDAD TIPO SINIESTRO • VP 3v3",
    "context": "Tienes a Whimsicott (Prankster) y Primarina frente a Incineroar (Tipo Fuego/Siniestro) y Archaludon. Quieres evitar que Incineroar use Parting Shot o Will-O-Wisp.",
    "oppSlots": [
      {
        "name": "Incineroar",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "hp": 80,
        "status": "Tipo Siniestro (Dark)"
      },
      {
        "name": "Archaludon",
        "item": "Leftovers",
        "ability": "Stamina",
        "hp": 85,
        "status": "Spe 105"
      }
    ],
    "mySlots": [
      {
        "name": "Whimsicott",
        "item": "Focus Sash",
        "ability": "Prankster",
        "hp": 100,
        "status": "Prankster Activo"
      },
      {
        "name": "Primarina",
        "item": "Mystic Water",
        "ability": "Liquid Voice",
        "hp": 85,
        "status": "Hyper Voice Ready"
      }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Whimsicott Moonblast en Archaludon + Primarina Hyper Voice en área",
        "optimal": true,
        "vpDelta": "+1.70 VP",
        "log": [
          "1. Whimsicott usa Moonblast (ataque de daño directo) sobre Archaludon (-32% HP).",
          "2. Primarina desata Hyper Voice potenciado en área: causa daño masivo super efectivo a Incineroar (-72% HP).",
          "3. Ambos rivales quedan en rango crítico sin que sus inmunidades afecten la jugada.",
          "4. Dominio del turno 3."
        ],
        "verdict": "✅ ÓPTIMO (+1.70 VP): Evitar lanzar movimientos de estado con Prankster a tipos Siniestro asegura daño productivo en la mesa."
      },
      {
        "id": "OPT-B",
        "label": "B) Whimsicott Taunt con Prankster en Incineroar + Primarina Moonblast en Archaludon",
        "optimal": false,
        "vpDelta": "-1.85 VP",
        "log": [
          "1. Whimsicott intenta usar Taunt (+1 prioridad por Prankster) hacia Incineroar.",
          "2. ¡Incineroar es de tipo Siniestro y es totalmente INMUNE a los movimientos de estado potenciados por Prankster!",
          "3. El Taunt falla por completo sin ningún efecto.",
          "4. Incineroar ejecuta Flare Blitz con STAB y pulveriza a Whimsicott de un solo golpe."
        ],
        "verdict": "❌ FUGA TÁCTICA (MEC-01 Dark Type Prankster Immunity): Los Pokémon de tipo Siniestro son inmunes a los movimientos de estado usados por Pokémon con Prankster (-1.85 VP)."
      },
      {
        "id": "OPT-C",
        "label": "C) Whimsicott Tailwind + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.30 VP",
        "log": [
          "1. Tailwind se activa con prioridad.",
          "2. Primarina usa Protect pero no genera daño.",
          "3. Incineroar desgasta a Whimsicott con Knock Off.",
          "4. Oportunidad ofensiva desaprovechada."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Play): Viento Afín sin presión ofensiva simultánea diluye la ventaja de velocidad (-1.30 VP)."
      },
      {
        "id": "OPT-D",
        "label": "D) Whimsicott Protect + Primarina Protect",
        "optimal": false,
        "vpDelta": "-1.25 VP",
        "log": [
          "1. Doble Protect pasivo.",
          "2. El rival no sufre ninguna presión.",
          "3. Cedes un turno limpio."
        ],
        "verdict": "❌ FUGA TÁCTICA (POS-03 Passive Protect): Doble Protect pasivo sin objetivo táctico (-1.25 VP)."
      }
    ]
  }
]

# Backward compatibility alias
FLASHCARD_SCENARIOS = CRUCIBLE_SCENARIOS
