# -*- coding: utf-8 -*-
"""
Generates the complete 42 Flash Card Scenarios with zero spoiler tokens in labels.
Updates engine/scenarios_data.py and data/Flashcard_Scenarios.csv.
"""

import sys
import re
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load current 42 scenarios
from engine.scenarios_data import FLASHCARD_SCENARIOS

# Specific realistic tactical options for SC-20 through SC-42
EXTENDED_23 = [
  # SC-20
  {
    "id": "SC-20",
    "title": "M330 Turno 3: TGT-01 Protect Tunneling vs Kingambit (15% HP)",
    "driver": "Tunnel_Vision",
    "code": "TGT-01",
    "turnBadge": "TURNO 3 • VP 3v3 • PRESIÓN DE PROTECT",
    "context": "Kingambit rival está a 15% HP pero tiene Protect cantado. A su lado Primarina (80% HP) prepara Hyper Voice. Tienes a Archaludon y a Incineroar en campo.",
    "oppSlots": [
      { "name": "Kingambit", "item": "Leftovers", "ability": "Defiant", "hp": 15, "status": "Protect Telegrafiado" },
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 80, "status": "Hyper Voice Ready" }
    ],
    "mySlots": [
      { "name": "Archaludon", "item": "Rocky Helmet", "ability": "Stamina", "hp": 85, "status": "Spe 105" },
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 70, "status": "Spe 80" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Archaludon Electro Shot en Primarina + Incineroar Knock Off en Primarina",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-21
  {
    "id": "SC-21",
    "title": "M331 Turno 2: TGT-02 Close Combat a Archaludon redirigido por Maushold Follow Me",
    "driver": "Tunnel_Vision",
    "code": "TGT-02",
    "turnBadge": "TURNO 2 • REDIRECCIÓN ACTIVA • VP 4v4",
    "context": "El rival tiene a Maushold (Friend Guard / Follow Me) protegiendo a Archaludon. Tienes a Lucario-Mega y Garchomp en campo.",
    "oppSlots": [
      { "name": "Maushold", "item": "Focus Sash", "ability": "Friend Guard", "hp": 100, "status": "Follow Me Ready" },
      { "name": "Archaludon", "item": "Rocky Helmet", "ability": "Stamina", "hp": 100, "status": "Spe 105" }
    ],
    "mySlots": [
      { "name": "Lucario-Mega", "item": "Lucarionite", "ability": "Adaptability", "hp": 100, "status": "Spe 180" },
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 100, "status": "Spe 169" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Lucario-Mega Aura Sphere en Maushold + Garchomp Earthquake",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-22
  {
    "id": "SC-22",
    "title": "M332 Turno 4: TGT-03 Double KO Waste en Pelipper (8% HP)",
    "driver": "Tunnel_Vision",
    "code": "TGT-03",
    "turnBadge": "TURNO 4 • VP 2v2 • RECURSOS CRÍTICOS",
    "context": "Pelipper rival está a 8% HP y cae ante cualquier golpe mínimo. A su lado Basculegion-M (100% HP) en lluvia amenaza con barrer. Tienes a Rillaboom y Primarina.",
    "oppSlots": [
      { "name": "Pelipper", "item": "Damp Rock", "ability": "Drizzle", "hp": 8, "status": "8% HP restante" },
      { "name": "Basculegion-M", "item": "Life Orb", "ability": "Swift Swim", "hp": 100, "status": "Swift Swim (Spe 260)" }
    ],
    "mySlots": [
      { "name": "Rillaboom", "item": "Miracle Seed", "ability": "Grassy Surge", "hp": 90, "status": "Grassy Glide Ready" },
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 75, "status": "Spe 80" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Grassy Glide en Basculegion + Primarina Moonblast en Basculegion",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-23
  {
    "id": "SC-23",
    "title": "M333 Turno 2: POS-01 Dry Switch hacia Draco Meteor de Archaludon",
    "driver": "Tunnel_Vision",
    "code": "POS-01",
    "turnBadge": "TURNO 2 • VP 3v3 • CONTROL DE ROTACIÓN",
    "context": "Tienes a Kingambit y Farigiraf en campo. El rival tiene a Archaludon y Pelipper en lluvia. Deseas meter a Dragonite para aprovechar Multiscale, pero Archaludon amenaza Draco Meteor.",
    "oppSlots": [
      { "name": "Archaludon", "item": "Rocky Helmet", "ability": "Stamina", "hp": 90, "status": "Draco Meteor Ready" },
      { "name": "Pelipper", "item": "Damp Rock", "ability": "Drizzle", "hp": 85, "status": "Rain 3T" }
    ],
    "mySlots": [
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 100, "status": "Spe 70" },
      { "name": "Farigiraf", "item": "Mental Herb", "ability": "Armor Tail", "hp": 90, "status": "Trick Room Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Kingambit Kowtow Cleave en Archaludon + Farigiraf Trick Room",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-24
  {
    "id": "SC-24",
    "title": "M334 Turno 3: MEC-01 Prioridad Grassy Glide a Sneasler en Terreno Psíquico",
    "driver": "Tunnel_Vision",
    "code": "MEC-01",
    "turnBadge": "TURNO 3 • PSYCHIC TERRAIN ACTIVO • VP 3v3",
    "context": "El rival tiene activo el Terreno Psíquico (invocado por Indeedee). Sneasler rival está a 30% HP y apoyado por Indeedee-F. Tienes a Rillaboom y Kingambit en campo.",
    "oppSlots": [
      { "name": "Sneasler", "item": "Focus Sash", "ability": "Unburden", "hp": 30, "status": "Grounded en Psychic Terrain" },
      { "name": "Indeedee-F", "item": "Psychic Seed", "ability": "Psychic Surge", "hp": 75, "status": "Psychic Terrain 3T" }
    ],
    "mySlots": [
      { "name": "Rillaboom", "item": "Miracle Seed", "ability": "Grassy Surge", "hp": 80, "status": "En Reserva/Campo" },
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 90, "status": "Sucker Punch Listo" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Wood Hammer en Indeedee-F + Kingambit Kowtow Cleave en Sneasler",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-25
  {
    "id": "SC-25",
    "title": "M335 Turno 2: TGT-02 Moonblast individual absorbido por Indeedee-F Follow Me",
    "driver": "Tunnel_Vision",
    "code": "TGT-02",
    "turnBadge": "TURNO 2 • EXPANDING FORCE AMENAZA • VP 4v4",
    "context": "El rival tiene a Indeedee-F (Follow Me) junto a Armarouge (Expanding Force en Terreno Psíquico). Tienes a Primarina y Garchomp en campo.",
    "oppSlots": [
      { "name": "Indeedee-F", "item": "Psychic Seed", "ability": "Psychic Surge", "hp": 100, "status": "Follow Me Ready" },
      { "name": "Armarouge", "item": "Twisted Spoon", "ability": "Flash Fire", "hp": 100, "status": "Expanding Force Ready" }
    ],
    "mySlots": [
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 100, "status": "Hyper Voice Ready" },
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 100, "status": "Stomping Tantrum / EQ" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Primarina Hyper Voice + Garchomp Stomping Tantrum en Indeedee-F",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-26
  {
    "id": "SC-26",
    "title": "M336 Turno 4: TGT-03 Overkill en Incineroar a 10% mientras Rillaboom carga Wood Hammer",
    "driver": "Tunnel_Vision",
    "code": "TGT-03",
    "turnBadge": "TURNO 4 • VP 2v2 • RECURSOS FINALES",
    "context": "Incineroar rival está a 10% HP y quemado. A su lado Rillaboom (100% HP) prepara Wood Hammer. Tienes a Charizard-Mega-Y y Kingambit.",
    "oppSlots": [
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 10, "status": "Burned (10% HP)" },
      { "name": "Rillaboom", "item": "Miracle Seed", "ability": "Grassy Surge", "hp": 100, "status": "Wood Hammer Ready" }
    ],
    "mySlots": [
      { "name": "Charizard-Mega-Y", "item": "Charizardite Y", "ability": "Drought", "hp": 85, "status": "Spe 167 (Sol Activo)" },
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 60, "status": "Spe 70" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard-Mega-Y Heat Wave + Kingambit Iron Head en Rillaboom",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-27
  {
    "id": "SC-27",
    "title": "M337 Turno 4: POS-03 Passive Protect abajo 2v4 en piezas vivas",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 4 • VP 2v4 • SITUACIÓN DE DESVENTAJA",
    "context": "Estás abajo 2v4 en piezas. Te quedan Primarina y Archaludon en campo frente a Garchomp e Incineroar. Necesitas remontar intercambiando KOs agresivamente.",
    "oppSlots": [
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 70, "status": "Spe 169" },
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 65, "status": "Spe 80" }
    ],
    "mySlots": [
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 70, "status": "Spe 80" },
      { "name": "Archaludon", "item": "Leftovers", "ability": "Stamina", "hp": 80, "status": "Spe 105" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Primarina Moonblast en Garchomp + Archaludon Body Press en Incineroar",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-28
  {
    "id": "SC-28",
    "title": "M338 Turno 2: Greed de Swords Dance con Garchomp ante Primarina Hyper Voice",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 2 • OFENSIVA EN CAMPO • VP 4v4",
    "context": "Tienes a Garchomp y Rotom-Wash en campo frente a Primarina y Archaludon. Tienes la oportunidad de noquear o presionar con ataques directos, pero te tienta usar Swords Dance.",
    "oppSlots": [
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 90, "status": "Hyper Voice Ready" },
      { "name": "Archaludon", "item": "Rocky Helmet", "ability": "Stamina", "hp": 85, "status": "Spe 105" }
    ],
    "mySlots": [
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 100, "status": "Spe 169" },
      { "name": "Rotom-Wash", "item": "Sitrus Berry", "ability": "Levitate", "hp": 100, "status": "Spe 115" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Garchomp Stomping Tantrum en Archaludon + Rotom-Wash Thunderbolt en Primarina",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-29
  {
    "id": "SC-29",
    "title": "M339 Turno 1: SPD-01 No Mega Evolucionar a Lucario para guardar sorpresa",
    "driver": "Greed",
    "code": "SPD-01",
    "turnBadge": "TURNO 1 • LEAD BATTLE • VP 4v4",
    "context": "Abres con Lucario (Lucarionite) y Farigiraf frente a Garchomp (Spe 169) e Incineroar. Decides no activar la Mega Evolución de Lucario creyendo que puedes 'guardar la sorpresa'.",
    "oppSlots": [
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 100, "status": "Spe 169" },
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 100, "status": "Spe 80" }
    ],
    "mySlots": [
      { "name": "Lucario", "item": "Lucarionite", "ability": "Inner Focus", "hp": 100, "status": "Spe 156 (Base 90)" },
      { "name": "Farigiraf", "item": "Mental Herb", "ability": "Armor Tail", "hp": 100, "status": "Spe 80" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Mega Evolucionar Lucario y usar Close Combat en Incineroar + Farigiraf Trick Room",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-30
  {
    "id": "SC-30",
    "title": "M340 Turno 2: MEC-01 Will-O-Wisp hacia Armarouge activando Flash Fire",
    "driver": "Greed",
    "code": "MEC-01",
    "turnBadge": "TURNO 2 • MECÁNICA DE HABILIDAD • VP 4v4",
    "context": "Armarouge rival y Indeedee-F están en campo. Tienes a Incineroar y Garchomp. Deseas neutralizar el daño físico del rival y consideras usar Will-O-Wisp hacia Armarouge.",
    "oppSlots": [
      { "name": "Armarouge", "item": "Twisted Spoon", "ability": "Flash Fire", "hp": 100, "status": "Flash Fire Inactivo" },
      { "name": "Indeedee-F", "item": "Psychic Seed", "ability": "Psychic Surge", "hp": 90, "status": "Follow Me Ready" }
    ],
    "mySlots": [
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 100, "status": "Knock Off Ready" },
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 100, "status": "Stomping Tantrum Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Knock Off en Armarouge + Garchomp Stomping Tantrum en Indeedee-F",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-31
  {
    "id": "SC-31",
    "title": "M341 Turno 3: Greed de Calm Mind Primarina ante Archaludon Electro Shot en Lluvia",
    "driver": "Greed",
    "code": "POS-03",
    "turnBadge": "TURNO 3 • LLUVIA ACTIVA • VP 3v3",
    "context": "Lluvia activa en campo. Archaludon rival prepara Electro Shot (carga instantánea en lluvia). A su lado Pelipper. Tienes a Primarina y Kingambit.",
    "oppSlots": [
      { "name": "Archaludon", "item": "Rocky Helmet", "ability": "Stamina", "hp": 90, "status": "Electro Shot Ready (Lluvia)" },
      { "name": "Pelipper", "item": "Damp Rock", "ability": "Drizzle", "hp": 70, "status": "Rain 3T" }
    ],
    "mySlots": [
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 85, "status": "Spe 80" },
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 95, "status": "Spe 70" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Kingambit Kowtow Cleave en Archaludon + Primarina Moonblast en Pelipper",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-32
  {
    "id": "SC-32",
    "title": "M342 Turno 1: Nasty Plot con Gengar-Mega en vez de cantar Perish Song o atacar",
    "driver": "Greed",
    "code": "SPD-01",
    "turnBadge": "TURNO 1 • SHADOW TAG LOCK • VP 4v4",
    "context": "Abres con Gengar-Mega y Incineroar frente a Primarina y Kingambit. Tienes a ambos rivales atrapados bajo Shadow Tag. Te tienta boostearte con Nasty Plot.",
    "oppSlots": [
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 100, "status": "Atrapado por Shadow Tag" },
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 100, "status": "Atrapado por Shadow Tag" }
    ],
    "mySlots": [
      { "name": "Gengar-Mega", "item": "Gengarite", "ability": "Shadow Tag", "hp": 100, "status": "Spe 200 (Post-Mega)" },
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 100, "status": "Fake Out Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Fake Out en Kingambit + Gengar-Mega Sludge Bomb en Primarina",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-33
  {
    "id": "SC-33",
    "title": "M343 Turno 3: POS-01 Dry Hard Switch por Tilt tras sufrir Golpe Crítico",
    "driver": "Tilt",
    "code": "POS-01",
    "turnBadge": "TURNO 3 • RESPUESTA EMOCIONAL • VP 3v3",
    "context": "En el turno anterior el rival conectó un golpe crítico inesperado contra tu lead. Sientes frustración y decides rotar en seco apresuradamente.",
    "oppSlots": [
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 85, "status": "Spe 169" },
      { "name": "Sneasler", "item": "Focus Sash", "ability": "Unburden", "hp": 70, "status": "Close Combat Ready" }
    ],
    "mySlots": [
      { "name": "Archaludon", "item": "Rocky Helmet", "ability": "Stamina", "hp": 65, "status": "Spe 105" },
      { "name": "Rotom-Wash", "item": "Sitrus Berry", "ability": "Levitate", "hp": 90, "status": "Will-O-Wisp Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rotom-Wash Will-O-Wisp en Garchomp + Archaludon Body Press en Sneasler",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-34
  {
    "id": "SC-34",
    "title": "M344 Turno 4: TGT-01 Atacar con rabia al slot que acaba de debilitar a tu compañero",
    "driver": "Tilt",
    "code": "TGT-01",
    "turnBadge": "TURNO 4 • FOCO EMOCIONAL • VP 2v2",
    "context": "Kingambit rival acaba de debilitar a tu Incineroar y sabes que su jugada estándar ahora es Protect. Sientes ira hacia ese slot y quieres atacarlo con todo.",
    "oppSlots": [
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 40, "status": "Protect Telegrafiado" },
      { "name": "Dragonite", "item": "Lum Berry", "ability": "Multiscale", "hp": 85, "status": "Extreme Speed Ready" }
    ],
    "mySlots": [
      { "name": "Lucario-Mega", "item": "Lucarionite", "ability": "Adaptability", "hp": 90, "status": "Spe 180" },
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 70, "status": "Spe 80" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Lucario-Mega Meteor Mash en Dragonite + Primarina Moonblast en Dragonite",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-35
  {
    "id": "SC-35",
    "title": "M345 Turno 2: Overprediction de doble cambio usando ataques de cobertura débiles",
    "driver": "Tilt",
    "code": "TGT-01",
    "turnBadge": "TURNO 2 • OVERPREDICTION • VP 4v4",
    "context": "El rival tiene a Pelipper y Basculegion en lluvia. Tienes a Rillaboom y Archaludon. Asumes que el rival 'obviamente' va a cambiar a sus dos slots y quieres castigar a los Pokémon entrantes.",
    "oppSlots": [
      { "name": "Pelipper", "item": "Damp Rock", "ability": "Drizzle", "hp": 90, "status": "Rain Active" },
      { "name": "Basculegion-M", "item": "Life Orb", "ability": "Swift Swim", "hp": 100, "status": "Swift Swim Active" }
    ],
    "mySlots": [
      { "name": "Rillaboom", "item": "Miracle Seed", "ability": "Grassy Surge", "hp": 100, "status": "Grassy Glide Ready" },
      { "name": "Archaludon", "item": "Leftovers", "ability": "Stamina", "hp": 100, "status": "Electro Shot Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Rillaboom Grassy Glide en Basculegion + Archaludon Electro Shot en Pelipper",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-36
  {
    "id": "SC-36",
    "title": "M346 Turno 3: POS-03 Protect consecutivo desesperado (33% de éxito)",
    "driver": "Tilt",
    "code": "POS-03",
    "turnBadge": "TURNO 3 • DECISIÓN DE VARIANZA • VP 2v2",
    "context": "Kingambit usó Protect el turno anterior con éxito y le queda 30% HP. Sientes desesperación y te tienta clickear Protect por segundo turno consecutivo.",
    "oppSlots": [
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 75, "status": "Spe 169" },
      { "name": "Charizard-Mega-Y", "item": "Charizardite Y", "ability": "Drought", "hp": 80, "status": "Sol Activo" }
    ],
    "mySlots": [
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 30, "status": "Protect usado en T2" },
      { "name": "Rotom-Wash", "item": "Sitrus Berry", "ability": "Levitate", "hp": 85, "status": "Hydro Pump Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Kingambit Sucker Punch en Charizard + Rotom-Wash Hydro Pump en Garchomp",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-37
  {
    "id": "SC-37",
    "title": "M347 Turno 1: Rushing Execution clickeando en segundo 42 sin revisar checklist",
    "driver": "Tilt",
    "code": "POS-02",
    "turnBadge": "TURNO 1 • APRESURAMIENTO • VP 4v4",
    "context": "Empieza el combate. El rival lidera con Sneasler e Incineroar. Tienes a Farigiraf y Primarina. Por prisa o nerviosismo clickeas tu primer impulso antes de revisar el tablero.",
    "oppSlots": [
      { "name": "Sneasler", "item": "Focus Sash", "ability": "Unburden", "hp": 100, "status": "Fake Out / Dire Claw" },
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 100, "status": "Fake Out / Knock Off" }
    ],
    "mySlots": [
      { "name": "Farigiraf", "item": "Mental Herb", "ability": "Armor Tail", "hp": 100, "status": "Armor Tail Activo" },
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 100, "status": "Hyper Voice Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Farigiraf Trick Room + Primarina Moonblast en Sneasler",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-38
  {
    "id": "SC-38",
    "title": "M348 Turno 2: MEC-02 Exponer a Talonflame a Sucker Punch en Terreno Psíquico",
    "driver": "Format_Divergence",
    "code": "MEC-02",
    "turnBadge": "TURNO 2 • MECÁNICA DE TERRENO • VP 3v3",
    "context": "Terreno Psíquico activo en mesa. Kingambit rival (Sucker Punch) está frente a tu Charizard-Mega-Y (Volador) y Farigiraf. Crees erróneamente que el Terreno Psíquico protege a Charizard de la prioridad.",
    "oppSlots": [
      { "name": "Kingambit", "item": "Black Glasses", "ability": "Defiant", "hp": 75, "status": "Sucker Punch Listo" },
      { "name": "Archaludon", "item": "Leftovers", "ability": "Stamina", "hp": 80, "status": "Spe 105" }
    ],
    "mySlots": [
      { "name": "Charizard-Mega-Y", "item": "Charizardite Y", "ability": "Drought", "hp": 45, "status": "Volador (Airborne)" },
      { "name": "Farigiraf", "item": "Mental Herb", "ability": "Armor Tail", "hp": 85, "status": "Armor Tail Activo" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Charizard-Mega-Y Protect + Farigiraf Hyper Voice",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-39
  {
    "id": "SC-39",
    "title": "M349 Turno 1: SPD-01 Creer que la velocidad de Mega Evolución aplica al turno siguiente",
    "driver": "Format_Divergence",
    "code": "SPD-01",
    "turnBadge": "TURNO 1 • REGLAS REGULATION M-C • VP 4v4",
    "context": "Tienes a Charizard (Charizardite Y) e Incineroar frente a Sneasler y Lucario. En formatos pre-Gen 7 las Megas no recalculaban velocidad el mismo turno; dudas sobre cuándo aplica el orden.",
    "oppSlots": [
      { "name": "Lucario", "item": "Life Orb", "ability": "Inner Focus", "hp": 100, "status": "Spe 156" },
      { "name": "Sneasler", "item": "Focus Sash", "ability": "Unburden", "hp": 100, "status": "Spe 189" }
    ],
    "mySlots": [
      { "name": "Charizard", "item": "Charizardite Y", "ability": "Solar Power", "hp": 100, "status": "Spe 167 (Post-Mega)" },
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 100, "status": "Fake Out Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Fake Out en Sneasler + Mega Evolucionar Charizard y usar Heat Wave",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-40
  {
    "id": "SC-40",
    "title": "M350 Turno 1: [ILLEGAL_FORMAT_SPECIES] Intento de uso de Amoonguss o Urshifu",
    "driver": "Format_Divergence",
    "code": "MEC-01",
    "turnBadge": "TURNO 1 • LEGALIDAD REGULATION M-C • VP 4v4",
    "context": "Estás planificando la selección de 4 Pokémon ante un equipo con Trick Room. Te tienta traer a Amoonguss con Spore o Urshifu para romper Protects, olvidando las restricciones de especies del formato.",
    "oppSlots": [
      { "name": "Farigiraf", "item": "Mental Herb", "ability": "Armor Tail", "hp": 100, "status": "Trick Room Setter" },
      { "name": "Torkoal", "item": "Charcoal", "ability": "Drought", "hp": 100, "status": "Erupción bajo TR" }
    ],
    "mySlots": [
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 100, "status": "Legal en Reg M-C" },
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 100, "status": "Legal en Reg M-C" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Incineroar Knock Off en Farigiraf + Primarina Hyper Voice en área",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-41
  {
    "id": "SC-41",
    "title": "M351 Turno 2: Asumir Assault Vest o Safety Goggles en el rival",
    "driver": "Format_Divergence",
    "code": "MEC-01",
    "turnBadge": "TURNO 2 • LEGALIDAD DE OBJETOS • VP 4v4",
    "context": "Te enfrentas a un Archaludon rival y calculas tu daño asumiendo que lleva Assault Vest o Safety Goggles, objetos restringidos o ausentes en Regulation_MC_Items.csv.",
    "oppSlots": [
      { "name": "Archaludon", "item": "Leftovers", "ability": "Stamina", "hp": 100, "status": "Leftovers Legal" },
      { "name": "Pelipper", "item": "Damp Rock", "ability": "Drizzle", "hp": 100, "status": "Damp Rock Legal" }
    ],
    "mySlots": [
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 100, "status": "Spe 80" },
      { "name": "Garchomp", "item": "Life Orb", "ability": "Rough Skin", "hp": 100, "status": "Spe 169" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Primarina Hyper Voice + Garchomp Stomping Tantrum en Archaludon",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

  # SC-42
  {
    "id": "SC-42",
    "title": "M352 Turno 3: MEC-01 Prankster Taunt de Whimsicott hacia Incineroar (Tipo Siniestro)",
    "driver": "Format_Divergence",
    "code": "MEC-01",
    "turnBadge": "TURNO 3 • INMUNIDAD TIPO SINIESTRO • VP 3v3",
    "context": "Tienes a Whimsicott (Prankster) y Primarina frente a Incineroar (Tipo Fuego/Siniestro) y Archaludon. Quieres evitar que Incineroar use Parting Shot o Will-O-Wisp.",
    "oppSlots": [
      { "name": "Incineroar", "item": "Sitrus Berry", "ability": "Intimidate", "hp": 80, "status": "Tipo Siniestro (Dark)" },
      { "name": "Archaludon", "item": "Leftovers", "ability": "Stamina", "hp": 85, "status": "Spe 105" }
    ],
    "mySlots": [
      { "name": "Whimsicott", "item": "Focus Sash", "ability": "Prankster", "hp": 100, "status": "Prankster Activo" },
      { "name": "Primarina", "item": "Mystic Water", "ability": "Liquid Voice", "hp": 85, "status": "Hyper Voice Ready" }
    ],
    "options": [
      {
        "id": "OPT-A",
        "label": "A) Whimsicott Moonblast en Archaludon + Primarina Hyper Voice en área",
        "optimal": True,
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
        "optimal": False,
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
        "optimal": False,
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
        "optimal": False,
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

# Clean SC-01 to SC-19 labels
CLEAN_BASE = []
for sc in FLASHCARD_SCENARIOS[:19]:
    sc_copy = dict(sc)
    new_opts = []
    for opt in sc["options"]:
        opt_copy = dict(opt)
        lbl = opt_copy["label"]
        # Clean specific phrases
        lbl = re.sub(r"\s*\(Control de Velocidad Seguro\)", "", lbl)
        lbl = re.sub(r"\s*\(Inversión de Velocidad\)", "", lbl)
        lbl = re.sub(r"\s*\(Área\)", "", lbl)
        lbl = re.sub(r"Dry Hard Switch\s*", "Cambiar ", lbl)
        lbl = re.sub(r"\s*\(18% HP\)", "", lbl)
        lbl = re.sub(r"\s*\(12% HP\)", "", lbl)
        lbl = re.sub(r"\s*\(Especie Ilegal fuera de Formato\)", " en la banca", lbl)
        opt_copy["label"] = lbl.strip()
        new_opts.append(opt_copy)
    sc_copy["options"] = new_opts
    CLEAN_BASE.append(sc_copy)

# Combine clean base (SC-01 to SC-19) with EXTENDED_23 (SC-20 to SC-42)
ALL_42 = CLEAN_BASE + EXTENDED_23
assert len(ALL_42) == 42, f"Expected 42, got {len(ALL_42)}"

# Verify no spoilers remain in ALL_42 options
spoilers = ['minimax', 'fuga', 'óptima', 'optima', 'pos-', 'tgt-', 'mec-', 'spd-', 'control de velocidad', 'inversión de velocidad']
violations = []
for sc in ALL_42:
    for opt in sc["options"]:
        lbl = opt["label"].lower()
        if any(sp in lbl for sp in spoilers):
            violations.append((sc["id"], opt["id"], opt["label"]))

if violations:
    print(f"FAILED: Found {len(violations)} spoilers:")
    for v in violations:
        print(v)
    sys.exit(1)

print("SUCCESS: All 42 scenarios verified with ZERO spoiler tokens in option labels!")

# Write to engine/scenarios_data.py
out_py = REPO_ROOT / "engine" / "scenarios_data.py"
with open(out_py, "w", encoding="utf-8") as f:
    f.write('true = True\nfalse = False\nnull = None\n# -*- coding: utf-8 -*-\n"""\nCoach Porygon VGC — Mode 3 Flashcard Sparring Scenarios\n42 Deterministic Scenarios (SC-01 to SC-42) with 4 options each (168 Total Options)\n"""\n\n')
    f.write("CRUCIBLE_SCENARIOS = ")
    import json
    f.write(json.dumps(ALL_42, indent=2, ensure_ascii=False))
    f.write("\n")

print(f"Updated {out_py}")

# Write to data/Flashcard_Scenarios.csv
out_csv = REPO_ROOT / "data" / "Flashcard_Scenarios.csv"
fieldnames = [
    "Scenario_ID", "Title", "Driver", "Error_Code", "Turn_Badge",
    "Opp_Slot1_Name", "Opp_Slot1_Item", "Opp_Slot1_Status",
    "Opp_Slot2_Name", "Opp_Slot2_Item", "Opp_Slot2_Status",
    "My_Slot1_Name", "My_Slot1_Item", "My_Slot1_Status",
    "My_Slot2_Name", "My_Slot2_Item", "My_Slot2_Status",
    "Context",
    "OptA_Label", "OptA_Optimal", "OptA_VP", "OptA_Verdict",
    "OptB_Label", "OptB_Optimal", "OptB_VP", "OptB_Verdict",
    "OptC_Label", "OptC_Optimal", "OptC_VP", "OptC_Verdict",
    "OptD_Label", "OptD_Optimal", "OptD_VP", "OptD_Verdict"
]

with open(out_csv, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for sc in ALL_42:
        opp = sc.get("oppSlots", [{}, {}])
        opp1 = opp[0] if len(opp) > 0 else {}
        opp2 = opp[1] if len(opp) > 1 else {}
        my = sc.get("mySlots", [{}, {}])
        my1 = my[0] if len(my) > 0 else {}
        my2 = my[1] if len(my) > 1 else {}
        opts = sc.get("options", [{}, {}, {}, {}])
        optA = opts[0] if len(opts) > 0 else {}
        optB = opts[1] if len(opts) > 1 else {}
        optC = opts[2] if len(opts) > 2 else {}
        optD = opts[3] if len(opts) > 3 else {}

        row = {
            "Scenario_ID": sc["id"],
            "Title": sc["title"],
            "Driver": sc["driver"],
            "Error_Code": sc["code"],
            "Turn_Badge": sc.get("turnBadge", ""),
            "Opp_Slot1_Name": opp1.get("name", ""),
            "Opp_Slot1_Item": opp1.get("item", ""),
            "Opp_Slot1_Status": opp1.get("status", ""),
            "Opp_Slot2_Name": opp2.get("name", ""),
            "Opp_Slot2_Item": opp2.get("item", ""),
            "Opp_Slot2_Status": opp2.get("status", ""),
            "My_Slot1_Name": my1.get("name", ""),
            "My_Slot1_Item": my1.get("item", ""),
            "My_Slot1_Status": my1.get("status", ""),
            "My_Slot2_Name": my2.get("name", ""),
            "My_Slot2_Item": my2.get("item", ""),
            "My_Slot2_Status": my2.get("status", ""),
            "Context": sc.get("context", ""),
            "OptA_Label": optA.get("label", ""),
            "OptA_Optimal": str(optA.get("optimal", "")),
            "OptA_VP": optA.get("vpDelta", ""),
            "OptA_Verdict": optA.get("verdict", ""),
            "OptB_Label": optB.get("label", ""),
            "OptB_Optimal": str(optB.get("optimal", "")),
            "OptB_VP": optB.get("vpDelta", ""),
            "OptB_Verdict": optB.get("verdict", ""),
            "OptC_Label": optC.get("label", ""),
            "OptC_Optimal": str(optC.get("optimal", "")),
            "OptC_VP": optC.get("vpDelta", ""),
            "OptC_Verdict": optC.get("verdict", ""),
            "OptD_Label": optD.get("label", ""),
            "OptD_Optimal": str(optD.get("optimal", "")),
            "OptD_VP": optD.get("vpDelta", ""),
            "OptD_Verdict": optD.get("verdict", "")
        }
        writer.writerow(row)

print(f"Updated {out_csv} with 42 scenarios.")
